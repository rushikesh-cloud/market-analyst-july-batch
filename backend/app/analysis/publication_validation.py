"""Validate terminal research against immutable registered evidence and artifacts."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .contracts import AgentResult, AnalysisError, ErrorCode, TechnicalDetails
from .models import AnalysisArtifact, AnalysisEvidence, AnalysisRun


def ensure_before_deadline(run: AnalysisRun, now: datetime) -> None:
    if run.deadline_at is not None and now >= run.deadline_at:
        raise AnalysisError(ErrorCode.DEADLINE_EXCEEDED)


def validate_registered_result(session: Session, result: AgentResult) -> None:
    evidence = {row.id: row.payload for row in session.scalars(
        select(AnalysisEvidence).where(AnalysisEvidence.run_id == result.run_id)
    )}
    for reference in result.evidence:
        if evidence.get(reference.id) != reference.model_dump(mode="json"):
            raise AnalysisError(ErrorCode.INVALID_OUTPUT)
    artifact_ids = {
        reference.source.artifact_id for reference in result.evidence
        if reference.source.artifact_id is not None
    }
    if isinstance(result.details, TechnicalDetails):
        artifact_ids.update(identifier for identifier in (
            result.details.chart_artifact_id, result.details.data_artifact_id,
        ) if identifier is not None)
    if artifact_ids:
        registered = set(session.scalars(select(AnalysisArtifact.id).where(
            AnalysisArtifact.run_id == result.run_id, AnalysisArtifact.id.in_(artifact_ids),
        )))
        if registered != artifact_ids:
            raise AnalysisError(ErrorCode.INVALID_OUTPUT)
