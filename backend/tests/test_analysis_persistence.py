"""C05: use actual PostgreSQL for migrations, transactions, and history."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from hashlib import sha256
from pathlib import Path
from threading import Barrier
import unittest
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import create_engine, delete, event, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import companies, migrate
from app.analysis.contracts import AgentResult, AgentType, AnalysisError, CompanySnapshot, ErrorCode, ModelConfiguration, SafeError
from app.analysis.fixtures import result_fixture
from app.analysis.models import AnalysisArtifact, AnalysisEvidence, AnalysisRun, utcnow
from app.analysis.repository import enqueue_run, get_run, list_runs, publish_terminal, require_postgres
from tests.analysis_postgres_support import isolated_postgres

MODEL = ModelConfiguration(deployment="synthetic-model", api_version="synthetic-version")


class AnalysisSQLiteBoundaryTests(unittest.TestCase):
    def test_C05_06_sqlite_company_crud_and_analysis_boundary(self):
        engine = create_engine("sqlite://")
        self.addCleanup(engine.dispose)
        companies.Base.metadata.create_all(engine)
        with Session(engine) as session:
            session.add(companies.Company(id="test", name="Example", ticker="EXAMPLE.NS"))
            session.commit()
            self.assertEqual(session.get(companies.Company, "test").name, "Example")
        with self.assertRaises(AnalysisError) as caught:
            require_postgres(engine)
        self.assertEqual(caught.exception.code, ErrorCode.POSTGRESQL_REQUIRED)


class AnalysisPersistenceTests(unittest.TestCase):
    def setUp(self):
        migration_case = self._testMethodName.startswith("test_C05_01")
        self.context = isolated_postgres(migrate=not migration_case)
        self.engine = self.context.__enter__()
        self.addCleanup(self.context.__exit__, None, None, None)
        if migration_case:
            directory = Path(migrate.__file__).resolve().parents[1] / "migrations"
            legacy = [path for path in sorted(directory.glob("*.sql")) if path.name < "006"]
            with patch.object(migrate, "engine", self.engine), patch.object(Path, "glob", return_value=legacy):
                migrate.migrate()
        self.company = self.add_company()

    def add_company(self):
        company = CompanySnapshot(id=str(uuid4()), name="Synthetic company", ticker=f"S{uuid4().hex[:8]}.NS")
        with Session(self.engine) as session:
            session.add(companies.Company(**company.model_dump()))
            session.commit()
        return company

    def queue(self, agent=AgentType.FUNDAMENTAL, company=None):
        return enqueue_run(self.engine, company or self.company, agent, MODEL)

    def start(self, run):
        now = utcnow()
        with Session(self.engine) as session:
            row = session.get(AnalysisRun, run.id)
            row.status = "running"
            row.attempt = 1
            row.lease_owner = "owner"
            row.lease_generation = 1
            row.as_of = now
            row.started_at = now
            row.deadline_at = now + timedelta(minutes=5)
            row.lease_expires_at = now + timedelta(seconds=60)
            session.commit()
        return get_run(self.engine, run.id)

    def finish(self, run, scenario="completed"):
        result = result_fixture(run.agent_type, scenario, run_id=run.id,
                                company=CompanySnapshot.model_validate(run.company_snapshot), as_of=run.as_of)
        with Session(self.engine) as session:
            for evidence in result.evidence:
                if session.get(AnalysisEvidence, (run.id, evidence.id)) is None:
                    session.add(AnalysisEvidence(
                        run_id=run.id, id=evidence.id,
                        fingerprint=sha256(evidence.model_dump_json().encode()).hexdigest(),
                        payload=evidence.model_dump(mode="json"),
                    ))
            session.commit()
        return publish_terminal(self.engine, run.id, "owner", 1, result=result)

    def test_C05_01_repeat_migration_preserves_existing_rows_and_namespaces(self):
        from app.documents import Document, DocumentChunk
        document_id = str(uuid4())
        with Session(self.engine) as session:
            session.add(Document(id=document_id, company_id=self.company.id, fiscal_year=2025,
                                 filename="synthetic.pdf", storage_path="synthetic.pdf"))
            session.flush()
            session.add(DocumentChunk(id=str(uuid4()), document_id=document_id, sequence=0,
                                      chunk_type="para", heading_path=[], content="Synthetic original", token_count=2))
            session.commit()
        with patch.object(migrate, "engine", self.engine):
            migrate.migrate()
            migrate.migrate()
        with self.engine.connect() as connection:
            self.assertEqual(connection.execute(text("SELECT count(*) FROM schema_migrations WHERE version='006_analysis_foundation.sql'")).scalar(), 1)
            self.assertEqual(connection.execute(text("SELECT content FROM document_chunks")).scalar(), "Synthetic original")
            self.assertEqual(connection.execute(text("SELECT count(*) FROM companies")).scalar(), 1)
            namespace = connection.execute(text("SELECT current_schema()")).scalar()
            for name in ("schema_migrations", "analysis_runs", "analysis_artifacts", "analysis_evidence", "companies", "documents", "document_chunks"):
                self.assertEqual(connection.execute(text("SELECT n.nspname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE c.oid=to_regclass(:name)"), {"name": name}).scalar(), namespace)
        indexes = inspect(self.engine).get_indexes("analysis_runs")
        self.assertEqual(sum(index["name"] == "uq_analysis_active_company_agent" for index in indexes), 1)

    def test_C05_02_two_connections_enforce_unique_active_run(self):
        barrier = Barrier(2)
        def insert_active(_):
            with Session(self.engine) as session:
                session.add(AnalysisRun(id=str(uuid4()), company_id=self.company.id,
                    company_snapshot=self.company.model_dump(mode="json"), agent_type="fundamental",
                    prompt_version="1", scoring_version="1", model_configuration=MODEL.model_dump(mode="json")))
                barrier.wait(timeout=10)
                try:
                    session.commit()
                    return "inserted"
                except IntegrityError:
                    session.rollback()
                    return "conflict"
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertCountEqual(pool.map(insert_active, range(2)), ["inserted", "conflict"])
        with ThreadPoolExecutor(max_workers=2) as pool:
            ids = list(pool.map(lambda _: self.queue().id, range(2)))
        self.assertEqual(ids[0], ids[1])
        # Force both repository calls past their initial SELECT before insertion.
        submission_barrier = Barrier(2)
        def synchronize_insert(session, context, instances):
            submission_barrier.wait(timeout=10)
        event.listen(Session, "before_flush", synchronize_insert)
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                raced_ids = list(pool.map(lambda _: self.queue(AgentType.TECHNICAL).id, range(2)))
            self.assertEqual(raced_ids[0], raced_ids[1])
        finally:
            event.remove(Session, "before_flush", synchronize_insert)
        self.assertNotEqual(self.queue(AgentType.NEWS).id, ids[0])
        self.assertNotEqual(self.queue(company=self.add_company()).id, ids[0])
        with self.assertRaises(IntegrityError):
            self.queue(company=self.company.model_copy(update={"id": str(uuid4())}))

    def test_C05_03_terminal_history_immutable_rerun_has_new_id(self):
        original = self.start(self.queue())
        completed = self.finish(original)
        rerun = self.queue()
        self.assertNotEqual(completed.id, rerun.id)
        with self.assertRaises(AnalysisError) as caught:
            self.finish(original)
        self.assertEqual(caught.exception.code, ErrorCode.LEASE_LOST)
        self.assertEqual(get_run(self.engine, original.id).result, completed.result)
        self.assertEqual([run.id for run in list_runs(self.engine, self.company.id)], [rerun.id, original.id])
        self.assertEqual(list_runs(self.engine, self.company.id, agent_type=AgentType.NEWS), [])

    def test_C05_04_document_deletion_retains_snapshot_company_fk_restricts(self):
        from app.documents import Document
        run = self.start(self.queue())
        result = result_fixture(run.agent_type, run_id=run.id, company=self.company, as_of=run.as_of)
        document_id = result.evidence[0].source.document_id
        with Session(self.engine) as session:
            session.add(Document(id=document_id, company_id=self.company.id, fiscal_year=2025,
                                 filename="synthetic.pdf", storage_path="synthetic.pdf"))
            session.add(AnalysisEvidence(run_id=run.id, id=result.evidence[0].id,
                fingerprint=sha256(b"snapshot").hexdigest(), payload=result.evidence[0].model_dump(mode="json")))
            session.commit()
        publish_terminal(self.engine, run.id, "owner", 1, result=result)
        with Session(self.engine) as session:
            session.execute(delete(Document).where(Document.id == document_id))
            session.commit()
            evidence = session.get(AnalysisEvidence, (run.id, result.evidence[0].id))
            self.assertEqual(evidence.payload["source"]["document_id"], document_id)
            self.assertEqual(evidence.payload["excerpt"], result.evidence[0].excerpt)
            with self.assertRaises(IntegrityError):
                session.execute(delete(companies.Company).where(companies.Company.id == self.company.id))
                session.commit()
            session.rollback()
        self.assertEqual(AgentResult.model_validate(get_run(self.engine, run.id).result), result)

    def test_C05_05_reconnect_preserves_all_terminal_states_versions_and_nulls(self):
        rows = []
        for agent, scenario in ((AgentType.FUNDAMENTAL, "completed"), (AgentType.TECHNICAL, "insufficient_data"), (AgentType.NEWS, "failed")):
            run = self.start(self.queue(agent))
            if scenario == "failed":
                finished = publish_terminal(self.engine, run.id, "owner", 1,
                    error=AnalysisError(ErrorCode.PROVIDER_UNAVAILABLE).as_safe_error())
            else:
                finished = self.finish(run, scenario)
            rows.append(finished)
        self.engine.dispose()
        for expected in rows:
            actual = get_run(self.engine, expected.id)
            self.assertEqual(actual.company_snapshot, self.company.model_dump(mode="json"))
            self.assertEqual(actual.model_configuration, MODEL.model_dump(mode="json"))
            self.assertEqual(actual.as_of, expected.as_of)
            self.assertIsNotNone(actual.as_of.tzinfo)
            self.assertEqual(actual.schema_version, "1.0")
            self.assertEqual(actual.result, expected.result)
            if actual.result:
                result = AgentResult.model_validate(actual.result)
                self.assertEqual(result.status.value, actual.status)
                if actual.status == "insufficient_data":
                    self.assertIsNone(result.final_score)
            else:
                self.assertEqual(SafeError.model_validate(actual.error).code, ErrorCode.PROVIDER_UNAVAILABLE)

    def test_fenced_terminal_write_rejects_wrong_identity_owner_and_expiry(self):
        run = self.start(self.queue())
        result = result_fixture(run.agent_type, run_id=run.id, company=self.company, as_of=run.as_of)
        for owner, generation, now in (("other", 1, utcnow()), ("owner", 0, utcnow()), ("owner", 1, run.lease_expires_at)):
            with self.assertRaises(AnalysisError) as caught:
                publish_terminal(self.engine, run.id, owner, generation, result=result, now=now)
            self.assertEqual(caught.exception.code, ErrorCode.LEASE_LOST)
        with self.assertRaises(AnalysisError) as caught:
            publish_terminal(self.engine, run.id, "owner", 1, result=result.model_copy(update={"company": self.add_company()}))
        self.assertEqual(caught.exception.code, ErrorCode.INVALID_OUTPUT)
        with self.assertRaises(ValueError):
            publish_terminal(self.engine, run.id, "owner", 1)
        self.assertEqual(get_run(self.engine, run.id).status, "running")
        self.assertIsNone(get_run(self.engine, "missing"))
        with self.assertRaises(ValueError):
            list_runs(self.engine, self.company.id, limit=101)
