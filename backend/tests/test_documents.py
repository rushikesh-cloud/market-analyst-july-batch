import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from app.auth import AuthenticatedUser, require_workspace_access
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import companies, documents, worker
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
        auth_override = patch.dict(app.dependency_overrides, {
            require_workspace_access: lambda: AuthenticatedUser('user_test', 'sess_test'),
        })
        auth_override.start()
        self.addCleanup(auth_override.stop)
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

    def test_content_and_chunks_are_filtered_by_page_after_parse(self):
        document = self.upload().json()
        document_id = document["id"]
        with Session(self.engine) as session:
            stored = session.get(documents.Document, document_id)
            stored.markdown = "# First\n\nPage one.\n\n<!-- PageBreak -->\n\n# Second\n\nPage two."
            session.add_all([
                documents.DocumentChunk(
                    id="chunk-1", document_id=document_id, sequence=0,
                    chunk_type="para", heading_path=["First"], content="Page one.",
                    overlap_text="", token_count=2, page_number=1,
                ),
                documents.DocumentChunk(
                    id="chunk-2", document_id=document_id, sequence=1,
                    chunk_type="para", heading_path=["Second"], content="Page two.",
                    overlap_text="Page one.", token_count=4, page_number=2,
                ),
            ])
            session.commit()

        content = self.client.get(f"/api/documents/{document_id}/content?page=2")
        self.assertEqual(content.status_code, 200)
        self.assertEqual(content.json(), {
            "markdown": "# Second\n\nPage two.", "page": 2, "page_count": 2
        })
        page = self.client.get(f"/api/documents/{document_id}/chunks?page=2").json()
        self.assertEqual(page["total"], 1)
        self.assertEqual(page["items"][0]["page_number"], 2)
        self.assertEqual(
            self.client.get(f"/api/documents/{document_id}/content?page=3").status_code,
            404,
        )


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.engine = create_engine(f"sqlite:///{self.root / 'worker.db'}")
        companies.Base.metadata.create_all(self.engine)
        self.patches = [
            patch.object(companies, "engine", self.engine),
            patch.object(documents, "engine", self.engine),
            patch.object(worker, "engine", self.engine),
            patch.object(documents, "workspace_root", self.root),
            patch.object(worker, "resolve_document_path", documents.resolve_document_path),
            patch.object(documents, "require_postgres", return_value=None),
        ]
        for item in self.patches:
            item.start()
        auth_override = patch.dict(app.dependency_overrides, {
            require_workspace_access: lambda: AuthenticatedUser('user_test', 'sess_test'),
        })
        auth_override.start()
        self.addCleanup(auth_override.stop)
        self.client = TestClient(app)
        company = self.client.post(
            "/api/companies", json={"name": "Microsoft", "ticker": "MSFT"}
        ).json()
        self.document = self.client.post(
            "/api/documents",
            data={"company_id": company["id"], "fiscal_year": "2025"},
            files={"file": ("report.pdf", b"%PDF-1.7\nreport", "application/pdf")},
        ).json()

    def tearDown(self):
        self.client.close()
        for item in reversed(self.patches):
            item.stop()
        self.engine.dispose()
        self.directory.cleanup()

    def test_worker_completes_claimed_run(self):
        owner = "test-worker"
        run_id = worker.claim_run(owner)
        body = " ".join(["details"] * 25)
        document_result = SimpleNamespace(content=f"# Results\n\nRevenue increased.\n\n## Details\n\n{body}")
        document_client = SimpleNamespace(
            begin_analyze_document=lambda *args, **kwargs: SimpleNamespace(
                result=lambda: document_result
            )
        )

        def embed(**kwargs):
            self.assertEqual(kwargs["input"], [f"Results > Details\nRevenue increased.\n\n{body}"])
            return SimpleNamespace(data=[
                SimpleNamespace(embedding=[0.1] * documents.EMBEDDING_DIMENSIONS)
                for _ in kwargs["input"]
            ])

        resources = SimpleNamespace(
            document_intelligence=lambda: document_client,
            openai=lambda: SimpleNamespace(embeddings=SimpleNamespace(create=embed)),
            settings=SimpleNamespace(
                openai=SimpleNamespace(embedding_deployment="embedding-small")
            ),
        )
        with patch.object(worker, "get_resource_clients", return_value=resources):
            worker.process_run(run_id, owner)

        status = self.client.get(f"/api/documents/{self.document['id']}/status").json()
        self.assertEqual(status["status"], "complete")
        self.assertEqual(status["stages"][-1]["status"], "complete")
        self.assertEqual(
            self.client.get(f"/api/documents/{self.document['id']}/chunks").json()["total"], 1
        )
        with Session(self.engine) as session:
            document = session.get(documents.Document, self.document["id"])
            self.assertEqual(document.chunking_version, documents.CHUNKING_VERSION)

    def test_worker_persists_provider_failure(self):
        owner = "test-worker"
        run_id = worker.claim_run(owner)
        resources = SimpleNamespace(
            document_intelligence=lambda: SimpleNamespace(
                begin_analyze_document=lambda *args, **kwargs: (_ for _ in ()).throw(
                    ValueError("provider unavailable")
                )
            )
        )
        with patch.object(worker, "get_resource_clients", return_value=resources):
            worker.process_run(run_id, owner)
        status = self.client.get(f"/api/documents/{self.document['id']}/status").json()
        self.assertEqual(status["status"], "failed")
        self.assertEqual(status["stages"][1]["status"], "failed")


if __name__ == "__main__":
    unittest.main()
