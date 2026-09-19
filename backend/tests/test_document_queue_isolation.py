"""Existing reports must remain untouched by startup and unrelated uploads."""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from app.auth import AuthenticatedUser, require_workspace_access
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app import companies, documents, main


class DocumentQueueIsolationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        self.engine = create_engine(f"sqlite:///{root / 'queue.db'}")
        self.addCleanup(self.engine.dispose)
        companies.Base.metadata.create_all(self.engine)
        # Exercise the PostgreSQL startup branch against isolated local records;
        # only schema migration and the engine's dialect/disposal are substituted.
        startup_engine = SimpleNamespace(
            dialect=SimpleNamespace(name="postgresql"), dispose=Mock()
        )
        for target, name, value in (
            (companies, "engine", self.engine),
            (documents, "engine", self.engine),
            (documents, "workspace_root", root),
            (documents, "require_postgres", Mock()),
            (main, "engine", startup_engine),
        ):
            patcher = patch.object(target, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        migration = patch("app.migrate.migrate")
        migration.start()
        self.addCleanup(migration.stop)
        auth_override = patch.dict(main.app.dependency_overrides, {
            require_workspace_access: lambda: AuthenticatedUser('user_test', 'sess_test'),
        })
        auth_override.start()
        self.addCleanup(auth_override.stop)
        self.client = TestClient(main.app)
        self.addCleanup(self.client.close)
        self.company = self.client.post(
            "/api/companies", json={"name": "Microsoft", "ticker": "MSFT"}
        ).json()
        self.existing_ids = []
        for year, status, version in (
            (2022, "complete", None),
            (2023, "complete", "page-header-v2"),
            (2024, "failed", "page-header-v2"),
            (2025, "complete", documents.CHUNKING_VERSION),
        ):
            document_id = self.upload(self.client, year).json()["id"]
            self.existing_ids.append(document_id)
            with Session(self.engine) as session:
                document = session.get(documents.Document, document_id)
                document.status = status
                document.markdown = "# Microsoft\n\nExisting report."
                document.chunking_version = version
                run = session.scalar(select(documents.IngestionRun).where(
                    documents.IngestionRun.document_id == document_id
                ))
                run.status = status
                run.finished_at = documents.utcnow()
                session.add(documents.DocumentChunk(
                    id=f"chunk-{year}", document_id=document_id, sequence=0,
                    page_number=1, chunk_type="para", heading_path=["Microsoft"],
                    content="Existing report.", overlap_text="", token_count=3,
                    embedding=[0.1] * documents.EMBEDDING_DIMENSIONS,
                ))
                session.commit()

    def upload(self, client, year, company_id=None):
        response = client.post(
            "/api/documents",
            data={"company_id": company_id or self.company["id"], "fiscal_year": str(year)},
            files={"file": ("report.pdf", b"%PDF-1.7\nreport", "application/pdf")},
        )
        self.assertEqual(response.status_code, 202, response.text)
        return response

    def existing_snapshot(self, client):
        return {
            document_id: {
                endpoint: client.get(f"/api/documents/{document_id}{endpoint}").json()
                for endpoint in ("", "/status", "/content", "/chunks")
            }
            for document_id in self.existing_ids
        }

    def assert_only_new_report_queued(self, client, before):
        company = client.post(
            "/api/companies", json={"name": "Bandhan Bank", "ticker": "BANDHANBNK.NS"}
        ).json()
        new_report = self.upload(client, 2026, company["id"]).json()
        self.assertEqual(new_report["status"], "queued")
        self.assertEqual(self.existing_snapshot(client), before)
        with Session(self.engine) as session:
            queued = session.scalars(select(documents.IngestionRun).where(
                documents.IngestionRun.status == "queued"
            )).all()
            self.assertEqual([run.document_id for run in queued], [new_report["id"]])

    def test_upload_only_queues_the_new_report(self):
        before = self.existing_snapshot(self.client)
        self.assert_only_new_report_queued(self.client, before)

    def test_restart_then_upload_preserves_existing_reports(self):
        before = self.existing_snapshot(self.client)
        with TestClient(main.app) as restarted_client:
            self.assert_only_new_report_queued(restarted_client, before)

    def test_explicit_retry_only_queues_the_selected_failed_report(self):
        before = self.existing_snapshot(self.client)
        failed_id = self.existing_ids[2]
        response = self.client.post(f"/api/documents/{failed_id}/retry")
        self.assertEqual(response.status_code, 202)
        after = self.existing_snapshot(self.client)
        self.assertEqual(after[failed_id]["/status"]["status"], "queued")
        self.assertEqual(after[failed_id]["/status"]["attempt"], 2)
        for document_id in self.existing_ids:
            if document_id != failed_id:
                self.assertEqual(after[document_id], before[document_id])


if __name__ == "__main__":
    unittest.main()
