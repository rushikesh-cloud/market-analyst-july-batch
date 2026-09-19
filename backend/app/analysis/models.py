"""Durable analysis rows; source documents are deliberately not foreign keys."""

from datetime import UTC, datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.companies import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


json_type = JSON().with_variant(JSONB(), "postgresql")


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"
    __table_args__ = (
        CheckConstraint("agent_type IN ('fundamental','technical','news')"),
        CheckConstraint("status IN ('queued','running','completed','insufficient_data','failed')"),
        CheckConstraint("attempt >= 0 AND lease_generation >= 0 AND model_calls >= 0 AND tool_calls >= 0"),
        Index("uq_analysis_active_company_agent", "company_id", "agent_type", unique=True,
              postgresql_where=text("status IN ('queued','running')"),
              sqlite_where=text("status IN ('queued','running')")),
        Index("ix_analysis_history", "company_id", "created_at", "id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    company_snapshot: Mapped[dict] = mapped_column(json_type)
    agent_type: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    as_of: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    lease_owner: Mapped[str | None] = mapped_column(String(200))
    lease_generation: Mapped[int] = mapped_column(Integer, default=0)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    progress: Mapped[dict] = mapped_column(json_type, default=dict)
    error: Mapped[dict | None] = mapped_column(json_type)
    result: Mapped[dict | None] = mapped_column(json_type)
    schema_version: Mapped[str] = mapped_column(String(50), default="1.0")
    prompt_version: Mapped[str] = mapped_column(String(200))
    scoring_version: Mapped[str] = mapped_column(String(200))
    model_version: Mapped[str | None] = mapped_column(String(200))
    model_configuration: Mapped[dict] = mapped_column(json_type)
    usage: Mapped[dict] = mapped_column(json_type, default=dict)
    model_calls: Mapped[int] = mapped_column(Integer, default=0)
    tool_calls: Mapped[int] = mapped_column(Integer, default=0)


class AnalysisEvidence(Base):
    __tablename__ = "analysis_evidence"
    __table_args__ = (UniqueConstraint("run_id", "fingerprint"),)

    run_id: Mapped[str] = mapped_column(ForeignKey("analysis_runs.id", ondelete="RESTRICT"), primary_key=True)
    id: Mapped[str] = mapped_column(String(200), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(json_type)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AnalysisArtifact(Base):
    __tablename__ = "analysis_artifacts"
    __table_args__ = (UniqueConstraint("run_id", "relative_path"), CheckConstraint("byte_size >= 0"))

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("analysis_runs.id", ondelete="RESTRICT"), index=True)
    relative_path: Mapped[str] = mapped_column(String(1000))
    mime_type: Mapped[str] = mapped_column(String(200))
    byte_size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    purpose: Mapped[str] = mapped_column(String(200))
    lease_generation: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
