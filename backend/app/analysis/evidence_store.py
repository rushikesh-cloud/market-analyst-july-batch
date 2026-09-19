"""Immutable, run-local evidence snapshots with lease-fenced publication."""

import hashlib
import json
from collections.abc import Callable
from datetime import datetime
from uuid import uuid4

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from .contracts import (
    AnalysisError, DataObservation, ErrorCode, EvidenceProvenance, EvidenceReference,
    EvidenceSource, EvidenceType,
)
from .models import AnalysisEvidence, utcnow
from .repository import owned_run, require_postgres
from .publication_validation import ensure_before_deadline


class EvidenceStore:
    def __init__(
        self, engine: Engine, run_id: str, owner: str | None = None,
        generation: int | None = None, *, clock: Callable[[], datetime] = utcnow,
    ):
        require_postgres(engine)
        self.engine, self.run_id = engine, run_id
        self.owner, self.generation, self.clock = owner, generation, clock

    def register(
        self, *, type: EvidenceType, source: EvidenceSource,
        excerpt: str | None, observation: DataObservation | None,
        provenance: EvidenceProvenance,
    ) -> EvidenceReference:
        if self.owner is None or self.generation is None:
            raise AnalysisError(ErrorCode.LEASE_LOST)
        evidence = EvidenceReference(
            id=str(uuid4()), run_id=self.run_id, type=type, source=source,
            excerpt=excerpt, observation=observation, provenance=provenance,
        )
        fingerprint_data = evidence.model_dump(mode="json", exclude={"id", "run_id"})
        # Re-reading identical content preserves the first retrieval provenance.
        fingerprint_data["provenance"].pop("retrieved_at")
        fingerprint = hashlib.sha256(json.dumps(
            fingerprint_data, sort_keys=True, separators=(",", ":"), allow_nan=False,
        ).encode()).hexdigest()
        with Session(self.engine) as session, session.begin():
            now = self.clock()
            run = owned_run(session, self.run_id, self.owner, self.generation, now)
            ensure_before_deadline(run, now)
            existing = session.scalar(select(AnalysisEvidence).where(
                AnalysisEvidence.run_id == self.run_id, AnalysisEvidence.fingerprint == fingerprint,
            ))
            if existing is not None:
                return EvidenceReference.model_validate(existing.payload)
            session.add(AnalysisEvidence(
                run_id=self.run_id, id=evidence.id, fingerprint=fingerprint,
                payload=evidence.model_dump(mode="json"),
            ))
        return evidence

    def get(self, evidence_id: str) -> EvidenceReference | None:
        with Session(self.engine) as session:
            evidence = session.get(AnalysisEvidence, (self.run_id, evidence_id))
            return EvidenceReference.model_validate(evidence.payload) if evidence is not None else None

    def list(self) -> tuple[EvidenceReference, ...]:
        with Session(self.engine) as session:
            return tuple(EvidenceReference.model_validate(row.payload) for row in session.scalars(
                select(AnalysisEvidence).where(AnalysisEvidence.run_id == self.run_id)
                .order_by(AnalysisEvidence.created_at, AnalysisEvidence.id)
            ))
