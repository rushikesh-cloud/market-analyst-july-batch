"""C06 durable storage tests with real PostgreSQL and temporary artifact volumes."""

import base64
import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.companies import Company
from app.analysis.artifact_store import ArtifactStore, artifact_root, _uuid
from app.analysis.contracts import (
    AgentResult, AgentType, AnalysisError, CompanySnapshot, ErrorCode,
    EvidenceProvenance, EvidenceSource, EvidenceType, ModelConfiguration,
)
from app.analysis.evidence_store import EvidenceStore
from app.analysis.fixtures import result_fixture
from app.analysis.models import AnalysisArtifact, AnalysisEvidence, AnalysisRun, utcnow
from app.analysis.publication_validation import ensure_before_deadline
from app.analysis.repository import enqueue_run, get_run, publish_terminal
from tests.analysis_postgres_support import isolated_postgres

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=')
MODEL = ModelConfiguration(deployment="synthetic", api_version="synthetic")


class ArtifactPathUnitTests(unittest.TestCase):
    def test_uuid_path_boundary_and_configured_root(self):
        identifier = str(uuid4())
        self.assertEqual(_uuid(identifier), identifier)
        for value in ("../", "/etc/passwd", "%2e%2e%2f", "not-uuid", None, identifier.upper()):
            with self.subTest(value=value), self.assertRaises(AnalysisError):
                _uuid(value)
        with patch.dict(os.environ, {"ANALYSIS_ARTIFACT_DIR": "/tmp/synthetic-artifacts"}):
            self.assertEqual(artifact_root(), Path("/tmp/synthetic-artifacts"))
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(artifact_root().name, "analysis-artifacts")


    def test_deadline_boundary_rejects_only_expired_publications(self):
        now = utcnow()
        ensure_before_deadline(AnalysisRun(deadline_at=None), now)
        ensure_before_deadline(AnalysisRun(deadline_at=now + timedelta(seconds=1)), now)
        for deadline in (now, now - timedelta(seconds=1)):
            with self.assertRaises(AnalysisError) as raised:
                ensure_before_deadline(AnalysisRun(deadline_at=deadline), now)
            self.assertEqual(raised.exception.code, ErrorCode.DEADLINE_EXCEEDED)


class AnalysisStorageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # One disposable schema; each case gets its own company/run IDs and real
        # committed transactions. Sharing migrations avoids redundant Azure DDL.
        cls.context = isolated_postgres()
        cls.engine = cls.context.__enter__()
        cls.addClassCleanup(cls.context.__exit__, None, None, None)

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'artifacts'
        self.company = CompanySnapshot(id=str(uuid4()), name="Synthetic", ticker=f"S{uuid4().hex[:10]}.NS")
        with Session(self.engine) as session:
            session.add(Company(**self.company.model_dump()))
            session.commit()
        self.run = self.start(AgentType.TECHNICAL)
        self.evidence = EvidenceStore(self.engine, self.run.id, "owner", 1)
        self.artifacts = ArtifactStore(self.engine, self.run.id, "owner", 1, root=self.root)

    def start(self, agent):
        queued = enqueue_run(self.engine, self.company, agent, MODEL)
        with Session(self.engine) as session:
            run = session.get(AnalysisRun, queued.id)
            run.status = "running"
            run.lease_owner = "owner"
            run.lease_generation = 1
            run.attempt = 1
            run.as_of = utcnow()
            run.started_at = run.as_of
            run.deadline_at = run.as_of + timedelta(minutes=5)
            run.lease_expires_at = run.as_of + timedelta(minutes=1)
            session.commit()
        return get_run(self.engine, queued.id)

    def register_evidence(self, store=None, *, time=None, artifact_id=None):
        return (store or self.evidence).register(
            type=EvidenceType.DATA_OBSERVATION,
            source=EvidenceSource(title="Synthetic source", artifact_id=artifact_id),
            excerpt="Synthetic immutable supporting content", observation=None,
            provenance=EvidenceProvenance(provider="synthetic", tool="fixture", retrieved_at=time or self.run.as_of),
        )

    def transfer_lease(self):
        with Session(self.engine) as session:
            run = session.get(AnalysisRun, self.run.id)
            run.lease_owner = "new-owner"
            run.lease_generation = 2
            run.attempt = 2
            run.lease_expires_at = utcnow() + timedelta(minutes=1)
            session.commit()

    def test_C06_01_register_restart_and_read_evidence_png(self):
        metadata = self.artifacts.write(PNG, mime_type="image/png", purpose="Synthetic chart")
        evidence = self.register_evidence(artifact_id=metadata.id)
        self.engine.dispose()
        reader = ArtifactStore(self.engine, self.run.id, root=self.root)
        restored = reader.read(metadata.id)
        self.assertEqual(restored.data, PNG)
        self.assertEqual(restored.metadata, metadata)
        self.assertEqual(metadata.sha256, hashlib.sha256(PNG).hexdigest())
        self.assertEqual(metadata.byte_size, len(PNG))
        self.assertEqual(metadata.mime_type, "image/png")
        self.assertNotIn("path", metadata.model_dump_json())
        ledger = EvidenceStore(self.engine, self.run.id)
        self.assertEqual(ledger.get(evidence.id), evidence)
        self.assertEqual(ledger.list(), (evidence,))
        self.assertIsNone(ledger.get("unknown"))
        with self.assertRaises(AnalysisError):
            self.register_evidence(store=ledger)
        with self.assertRaises(AnalysisError):
            reader.write(PNG, mime_type="image/png", purpose="Read-only")
        with self.assertRaises(TypeError):
            self.artifacts.write("not bytes", mime_type="text/plain", purpose="Invalid")

    def test_C06_02_paths_mismatched_runs_and_symlinks_never_escape(self):
        metadata = self.artifacts.write(PNG, mime_type="image/png", purpose="Synthetic chart")
        other = self.start(AgentType.NEWS)
        for artifact_id in (metadata.id, str(uuid4()), "../", "/etc/passwd", "%2e%2e%2f"):
            with self.subTest(id=artifact_id), self.assertRaises(AnalysisError) as raised:
                ArtifactStore(self.engine, other.id, root=self.root).read(artifact_id)
            self.assertEqual(raised.exception.code, ErrorCode.ARTIFACT_UNAVAILABLE)
        with Session(self.engine) as session:
            original = session.get(AnalysisArtifact, metadata.id).relative_path
        for path in ("../outside", "/etc/passwd", "%2e%2e%2f", f"{other.id}/attempt-1/{metadata.id}.bin"):
            with Session(self.engine) as session:
                session.get(AnalysisArtifact, metadata.id).relative_path = path
                session.commit()
            with self.assertRaises(AnalysisError):
                self.artifacts.read(metadata.id)
        with Session(self.engine) as session:
            session.get(AnalysisArtifact, metadata.id).relative_path = original
            session.commit()
        outside = Path(self.temp.name) / "outside"
        outside.write_bytes(b"must never read")
        path = self.root / original
        path.unlink()
        path.symlink_to(outside)
        with self.assertRaises(AnalysisError):
            self.artifacts.read(metadata.id)
        path.unlink()
        path.write_bytes(PNG)
        # Protect against a symlink replacing the run directory too.
        run_directory = self.root / self.run.id
        backup = self.root / "saved-run"
        run_directory.rename(backup)
        run_directory.symlink_to(backup, target_is_directory=True)
        with self.assertRaises(AnalysisError):
            self.artifacts.read(metadata.id)
        with self.assertRaises(OSError):
            self.artifacts.write(PNG, mime_type="image/png", purpose="No symlink write")
        run_directory.unlink()
        backup.rename(run_directory)
        # Special files cannot block a read indefinitely.
        path.unlink()
        os.mkfifo(path)
        with self.assertRaises(AnalysisError):
            self.artifacts.read(metadata.id)
        self.assertEqual(outside.read_bytes(), b"must never read")

    def test_C06_03_interrupted_write_and_failed_registration_never_available(self):
        with patch('app.analysis.artifact_store.os.fsync', side_effect=OSError("synthetic disk failure")):
            with self.assertRaises(OSError):
                self.artifacts.write(PNG, mime_type="image/png", purpose="Interrupted")
        self.assertEqual(list(self.root.rglob('*.bin')), [])
        self.assertEqual(list(self.root.rglob('*.partial')), [])
        with patch.object(self.artifacts, '_register', side_effect=RuntimeError("synthetic registration failure")):
            with self.assertRaises(RuntimeError):
                self.artifacts.write(PNG, mime_type="image/png", purpose="Failed registration")
        self.assertEqual(list(self.root.rglob('*.bin')), [])
        with Session(self.engine) as session:
            self.assertEqual(list(session.scalars(select(AnalysisArtifact).where(AnalysisArtifact.run_id == self.run.id))), [])
        # Even an abruptly abandoned file is never served without a registry row.
        orphan_id = str(uuid4())
        (self.root / self.run.id / 'attempt-1' / f'{orphan_id}.bin').write_bytes(PNG)
        with self.assertRaises(AnalysisError):
            self.artifacts.read(orphan_id)

    def test_C06_04_deduplicates_within_run_preserves_independent_provenance(self):
        with ThreadPoolExecutor(max_workers=2) as executor:
            entries = list(executor.map(lambda _: self.register_evidence(), range(2)))
        self.assertEqual(entries[0], entries[1])
        later = self.register_evidence(time=self.run.as_of + timedelta(seconds=5))
        self.assertEqual(later, entries[0])
        self.assertEqual(len(self.evidence.list()), 1)
        other = self.start(AgentType.NEWS)
        other_store = EvidenceStore(self.engine, other.id, "owner", 1)
        independent = self.register_evidence(store=other_store, time=other.as_of)
        self.assertNotEqual(independent.id, entries[0].id)
        self.assertEqual(independent.run_id, other.id)
        self.assertEqual(independent.provenance.retrieved_at, other.as_of)
        self.assertIsNone(other_store.get(entries[0].id))

    def test_C06_05_missing_and_corrupt_files_are_safe_outcomes(self):
        first = self.artifacts.write(PNG, mime_type="image/png", purpose="First")
        intact = self.artifacts.write(PNG, mime_type="image/png", purpose="Intact")
        path = self.root / self.run.id / 'attempt-1' / f'{first.id}.bin'
        path.write_bytes(b"corrupt")
        with self.assertRaises(AnalysisError) as raised:
            self.artifacts.read(first.id)
        self.assertEqual(raised.exception.code, ErrorCode.ARTIFACT_CORRUPT)
        path.write_bytes(b'x' * len(PNG))
        with self.assertRaises(AnalysisError) as raised:
            self.artifacts.read(first.id)
        self.assertEqual(raised.exception.code, ErrorCode.ARTIFACT_CORRUPT)
        path.unlink()
        with self.assertRaises(AnalysisError) as raised:
            self.artifacts.read(first.id)
        self.assertEqual(raised.exception.code, ErrorCode.ARTIFACT_UNAVAILABLE)
        self.assertNotIn(str(self.root), str(raised.exception))
        self.assertEqual(self.artifacts.read(intact.id).data, PNG)
        self.assertEqual(get_run(self.engine, self.run.id).status, "running")

    def test_C06_06_expired_worker_cannot_publish_after_transfer(self):
        original_register = self.artifacts._register
        def transfer_before_register(metadata, relative_path):
            self.transfer_lease()
            original_register(metadata, relative_path)
        with patch.object(self.artifacts, '_register', side_effect=transfer_before_register):
            with self.assertRaises(AnalysisError) as raised:
                self.artifacts.write(PNG, mime_type="image/png", purpose="Stale attempt")
        self.assertEqual(raised.exception.code, ErrorCode.LEASE_LOST)
        self.assertEqual(list(self.root.rglob('*.bin')), [])
        current = ArtifactStore(self.engine, self.run.id, "new-owner", 2, root=self.root)
        metadata = current.write(PNG, mime_type="image/png", purpose="Current attempt")
        with self.assertRaises(AnalysisError):
            self.artifacts.write(b"stale", mime_type="text/plain", purpose="Stale overwrite")
        with self.assertRaises(AnalysisError):
            self.register_evidence()
        self.assertEqual(current.read(metadata.id).data, PNG)
        self.assertTrue((self.root / self.run.id / 'attempt-2' / f'{metadata.id}.bin').exists())

    def test_expired_deadline_blocks_files_evidence_and_results_but_allows_safe_failure(self):
        with Session(self.engine) as session:
            session.get(AnalysisRun, self.run.id).deadline_at = self.run.as_of
            session.commit()
        operations = (
            lambda: self.artifacts.write(PNG, mime_type="image/png", purpose="Too late"),
            lambda: self.register_evidence(),
            lambda: publish_terminal(self.engine, self.run.id, "owner", 1,
                result=result_fixture(AgentType.TECHNICAL, "insufficient_data", run_id=self.run.id,
                                      company=self.company, as_of=self.run.as_of)),
        )
        for operation in operations:
            with self.assertRaises(AnalysisError) as raised:
                operation()
            self.assertEqual(raised.exception.code, ErrorCode.DEADLINE_EXCEEDED)
        finished = publish_terminal(self.engine, self.run.id, "owner", 1,
            error=AnalysisError(ErrorCode.DEADLINE_EXCEEDED).as_safe_error())
        self.assertEqual(finished.status, "failed")
        self.assertEqual(finished.error["code"], "deadline_exceeded")

    def test_terminal_publication_requires_exact_snapshots_and_registered_artifacts(self):
        chart = self.artifacts.write(PNG, mime_type="image/png", purpose="Chart")
        data = self.artifacts.write(b'{}', mime_type="application/json", purpose="Data snapshot")
        evidence = self.register_evidence(artifact_id=chart.id)
        raw = result_fixture(AgentType.TECHNICAL, run_id=self.run.id, company=self.company, as_of=self.run.as_of).model_dump_json()
        payload = json.loads(raw.replace('evidence-1', evidence.id).replace('chart-1', chart.id).replace('data-1', data.id))
        payload['evidence'] = [evidence.model_dump(mode='json')]
        result = AgentResult.model_validate(payload)
        # Same valid run-local ID but fabricated content cannot be published.
        tampered = json.loads(json.dumps(payload))
        tampered['evidence'][0]['excerpt'] = 'Fabricated replacement'
        with self.assertRaises(AnalysisError) as raised:
            publish_terminal(self.engine, self.run.id, 'owner', 1, result=AgentResult.model_validate(tampered))
        self.assertEqual(raised.exception.code, ErrorCode.INVALID_OUTPUT)
        for key in ('chart_artifact_id', 'data_artifact_id'):
            tampered = json.loads(json.dumps(payload))
            tampered['details'][key] = str(uuid4())
            with self.assertRaises(AnalysisError):
                publish_terminal(self.engine, self.run.id, 'owner', 1, result=AgentResult.model_validate(tampered))
        self.assertEqual(get_run(self.engine, self.run.id).status, 'running')
        completed = publish_terminal(self.engine, self.run.id, 'owner', 1, result=result)
        self.assertEqual(AgentResult.model_validate(completed.result), result)
        self.engine.dispose()
        self.assertEqual(self.artifacts.read(chart.id).data, PNG)
        self.assertEqual(self.evidence.get(evidence.id), evidence)
        # Result's source artifact reference is independently fenced, too.
        other = self.start(AgentType.FUNDAMENTAL)
        source_artifact = self.register_evidence(EvidenceStore(self.engine, other.id, 'owner', 1), artifact_id=chart.id)
        fundamental = result_fixture(AgentType.FUNDAMENTAL, run_id=other.id, company=self.company, as_of=other.as_of)
        raw = fundamental.model_dump_json().replace('evidence-1', source_artifact.id)
        payload = json.loads(raw)
        payload['evidence'] = [source_artifact.model_dump(mode='json')]
        with self.assertRaises(AnalysisError):
            publish_terminal(self.engine, other.id, 'owner', 1, result=AgentResult.model_validate(payload))


if __name__ == '__main__':
    unittest.main()
