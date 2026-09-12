import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from app import companies, documents
from app.main import app


class DocumentApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.engine = create_engine(f"sqlite:///{self.root / 'test.db'}")
        companies.Base.metadata.create_all(self.engine)
        self.patches = [
            patch.object(companies, "engine", self.engine),
            patch.object(documents, "engine", self.engine),
            patch.object(documents, "workspace_root", self.root),
            patch.object(documents, "require_postgres", return_value=None),
        ]
        for item in self.patches:
            item.start()
        self.client = TestClient(app)
        self.company = self.client.post(
            "/api/companies", json={"name": "Microsoft", "ticker": "MSFT"}
        ).json()

    def tearDown(self):
        self.client.close()
        for item in reversed(self.patches):
            item.stop()
        self.engine.dispose()
        self.directory.cleanup()

    def upload(self, year=2025, content=b"%PDF-1.7\nreport"):
        return self.client.post(
            "/api/documents",
            data={"company_id": self.company["id"], "fiscal_year": str(year)},
            files={"file": ("annual-report.pdf", content, "application/pdf")},
        )

    def test_upload_list_detail_and_duplicate(self):
        response = self.upload()
        self.assertEqual(response.status_code, 202)
        document = response.json()
        self.assertEqual(document["status"], "queued")
        self.assertEqual(document["company"]["name"], "Microsoft")
        self.assertEqual(self.client.get("/api/documents").json(), [document])
        self.assertEqual(
            self.client.get(f"/api/documents/{document['id']}").json()["id"],
            document["id"],
        )
        self.assertEqual(self.upload().status_code, 409)

    def test_upload_validation_and_safe_relative_storage(self):
        self.assertEqual(self.upload(content=b"not a pdf").status_code, 422)
        self.assertEqual(self.upload(year=1899).status_code, 422)
        response = self.upload()
        stored = response.json()["storage_path"]
        self.assertFalse(Path(stored).is_absolute())
        self.assertTrue((self.root / stored).is_file())
        with self.assertRaises(ValueError):
            documents.resolve_document_path("../outside.pdf")

    def test_delete_removes_file_and_unblocks_company_year(self):
        document = self.upload().json()
        stored = self.root / document["storage_path"]
        self.assertEqual(
            self.client.delete(f"/api/companies/{self.company['id']}").status_code, 409
        )
        self.assertEqual(self.client.delete(f"/api/documents/{document['id']}").status_code, 204)
        self.assertFalse(stored.exists())
        self.assertEqual(self.upload().status_code, 202)

    def test_status_content_chunks_and_retry(self):
        document = self.upload().json()
        document_id = document["id"]
        status = self.client.get(f"/api/documents/{document_id}/status")
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json()["stages"][0]["name"], "queued")
        self.assertEqual(
            self.client.get(f"/api/documents/{document_id}/content").status_code, 409
        )
        self.assertEqual(
            self.client.get(f"/api/documents/{document_id}/chunks").json()["items"], []
        )
        self.assertEqual(
            self.client.post(f"/api/documents/{document_id}/retry").status_code, 409
        )


class ChunkingTests(unittest.TestCase):
    def test_heading_tables_order_and_non_recursive_overlap(self):
        markdown = """# Overview

First paragraph with introductory facts.

## Metrics

| Year | Revenue |
| --- | --- |
| 2024 | 100 |

Closing paragraph.
"""
        chunks = documents.chunk_markdown(markdown, max_tokens=2000, overlap_tokens=5)
        self.assertEqual([chunk.chunk_type for chunk in chunks], ["para", "table", "para"])
        self.assertEqual(chunks[1].heading_path, ["Overview", "Metrics"])
        self.assertTrue(chunks[1].overlap_text)
        self.assertNotIn(chunks[0].overlap_text, chunks[1].overlap_text)
        self.assertEqual([chunk.sequence for chunk in chunks], [0, 1, 2])

    def test_chunk_inputs_respect_token_limit(self):
        markdown = "# Long section\n\n" + "word " * 100
        chunks = documents.chunk_markdown(markdown, max_tokens=30, overlap_tokens=5)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(chunk.token_count <= 30 for chunk in chunks))


if __name__ == "__main__":
    unittest.main()
