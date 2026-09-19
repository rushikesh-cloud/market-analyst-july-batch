"""Search API contract and PostgreSQL hybrid retrieval integration tests."""
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app import companies, documents
from app.main import app


class SearchApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.engine = create_engine(f"sqlite:///{self.directory.name}/search.db")
        companies.Base.metadata.create_all(self.engine)
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.engine.dispose()
        self.directory.cleanup()

    def test_rejects_invalid_search_inputs(self):
        for payload in [
            {}, {"query": "  "}, {"query": "a" * 2001},
            {"query": "profit", "k": 0}, {"query": "profit", "k": 101},
            {"query": "profit", "k": 1.5},
            {"query": "profit", "max_tokens": 0},
            {"query": "profit", "max_tokens": 100001},
        ]:
            with self.subTest(payload=str(payload)[:80]):
                response = self.client.post('/api/documents/unknown/search', json=payload)
                self.assertEqual(response.status_code, 422)

    def test_missing_deleted_and_unready_documents(self):
        from app import document_search
        with Session(self.engine) as session:
            session.add(companies.Company(id='company', name='Search', ticker='SEARCH'))
            for identifier, status in [('queued', 'queued'), ('deleted', 'complete')]:
                session.add(documents.Document(
                    id=identifier, company_id='company', fiscal_year=2024 if identifier == 'queued' else 2025,
                    filename='test.pdf', storage_path='test.pdf', status=status,
                    deleted_at=documents.utcnow() if identifier == 'deleted' else None,
                ))
            session.commit()
        with patch.object(document_search, 'engine', self.engine), patch.object(document_search, 'require_postgres'):
            for identifier, expected in [('unknown', 404), ('deleted', 404), ('queued', 409)]:
                response = self.client.post(f'/api/documents/{identifier}/search', json={'query': 'profit'})
                self.assertEqual(response.status_code, expected)


@unittest.skipUnless(os.getenv('RUN_SEARCH_POSTGRES_TESTS') == '1', 'Requires isolated PostgreSQL test schema')
class PostgresSearchTests(unittest.TestCase):
    def setUp(self):
        from app import document_search
        self.search = document_search
        self.connection = companies.engine.connect()
        self.transaction = self.connection.begin()
        self.schema = 'search_test_' + uuid4().hex
        self.connection.execute(text(f'CREATE SCHEMA {self.schema}'))
        self.connection.execute(text(f'SET LOCAL search_path TO {self.schema}, public'))
        companies.Base.metadata.create_all(self.connection)
        migration = Path(__file__).resolve().parents[1] / 'migrations/004_chunk_full_text_search.sql'
        self.connection.execute(text(migration.read_text()))
        self.embedding = [1.0] + [0.0] * (documents.EMBEDDING_DIMENSIONS - 1)
        with Session(self.connection) as session:
            session.add(companies.Company(id='company', name='Search', ticker='SEARCH'))
            for identifier, year in [('report', 2025), ('other', 2024)]:
                session.add(documents.Document(
                    id=identifier, company_id='company', fiscal_year=year,
                    filename='test.pdf', storage_path='test.pdf', status='complete',
                    embedding_deployment='stored-model', embedding_dimensions=documents.EMBEDDING_DIMENSIONS,
                ))
            session.flush()
            for i in range(15):
                session.add(documents.DocumentChunk(
                    id=f'chunk-{i}', document_id='report', sequence=i, page_number=i + 1,
                    chunk_type='para', heading_path=['Results'], overlap_text='',
                    content='profit grew strongly' if i == 1 else f'Financial discussion {i}',
                    token_count=100 if i != 0 else 400,
                    embedding=[1.0, i / 20] + [0.0] * (documents.EMBEDDING_DIMENSIONS - 2),
                ))
            session.add(documents.DocumentChunk(
                id='foreign', document_id='other', sequence=0, page_number=1,
                chunk_type='para', heading_path=[], overlap_text='', content='profit profit profit',
                token_count=1, embedding=self.embedding,
            ))
            session.commit()
        self.provider = SimpleNamespace(openai=lambda: SimpleNamespace(
            with_options=lambda **kwargs: SimpleNamespace(embeddings=SimpleNamespace(create=self.embed))
        ))
        self.patches = [patch.object(document_search, 'engine', self.connection),
                        patch.object(document_search, 'require_postgres'),
                        patch.object(document_search, 'get_resource_clients', return_value=self.provider)]
        for item in self.patches:
            item.start()
        self.client = TestClient(app)

    def embed(self, **kwargs):
        self.assertEqual(kwargs['model'], 'stored-model')
        self.assertEqual(kwargs['input'], ['profit'])
        return SimpleNamespace(data=[SimpleNamespace(embedding=self.embedding)])

    def tearDown(self):
        self.client.close()
        for item in reversed(self.patches):
            item.stop()
        self.transaction.rollback()
        self.connection.close()

    def search_request(self, **kwargs):
        return self.client.post('/api/documents/report/search', json={'query': ' profit ', **kwargs})

    def test_combines_rankings_scopes_document_and_defaults_to_ten(self):
        response = self.search_request()
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(len(body['items']), 10)
        self.assertEqual(body['query'], 'profit')
        self.assertEqual(body['items'][0]['id'], 'chunk-1')
        self.assertEqual(body['items'][0]['semantic_rank'], 2)
        self.assertEqual(body['items'][0]['text_rank'], 1)
        self.assertNotIn('foreign', [item['id'] for item in body['items']])
        self.assertEqual(body['total_tokens'], sum(item['token_count'] for item in body['items']))

    def test_budget_keeps_ranked_whole_chunks_and_k_limits_count(self):
        body = self.search_request(k=3, max_tokens=250).json()
        self.assertEqual([item['id'] for item in body['items']], ['chunk-1', 'chunk-2'])
        self.assertEqual(body['total_tokens'], 200)
        self.assertTrue(body['budget_limited'])
        self.assertEqual(len(self.search_request(k=2).json()['items']), 2)
        body = self.search_request(max_tokens=1).json()
        self.assertEqual(body['items'], [])
        self.assertTrue(body['budget_limited'])

    def test_empty_document(self):
        self.connection.execute(text("DELETE FROM document_chunks WHERE document_id = 'report'"))
        response = self.search_request()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['items'], [])

    def test_provider_failure_and_dimensions_have_safe_errors(self):
        with patch.object(self.provider, 'openai', side_effect=RuntimeError('secret provider details')):
            response = self.search_request()
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('secret provider details', response.text)
        self.embedding = [1.0]
        response = self.search_request()
        self.assertEqual(response.status_code, 503)

    def test_stored_embedding_metadata_required(self):
        self.connection.execute(text("UPDATE documents SET embedding_deployment = NULL WHERE id = 'report'"))
        self.assertEqual(self.search_request().status_code, 409)


if __name__ == '__main__':
    unittest.main()
