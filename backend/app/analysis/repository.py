"""PostgreSQL persistence with immutable history and fenced terminal publication."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .contracts import (
    AgentResult, AgentType, AnalysisError, CompanySnapshot, ErrorCode,
    ModelConfiguration, SafeError,
)
from .models import AnalysisRun, utcnow

ACTIVE_STATUSES = ("queued", "running")


def require_postgres(engine: Engine) -> None:
    if engine.dialect.name != "postgresql":
        raise AnalysisError(ErrorCode.POSTGRESQL_REQUIRED)


def enqueue_run(
    engine: Engine, company: CompanySnapshot, agent_type: AgentType,
    model: ModelConfiguration,
) -> AnalysisRun:
    """Return the existing active run when concurrent submissions collide."""
    require_postgres(engine)
    agent_type = AgentType(agent_type)
    with Session(engine, expire_on_commit=False) as session:
        active = session.scalar(select(AnalysisRun).where(
            AnalysisRun.company_id == company.id, AnalysisRun.agent_type == agent_type,
            AnalysisRun.status.in_(ACTIVE_STATUSES),
        ))
        if active is not None:
            return active
        run = AnalysisRun(
            id=str(uuid4()), company_id=company.id,
            company_snapshot=company.model_dump(mode="json"), agent_type=agent_type,
            model_configuration=model.model_dump(mode="json"),
            prompt_version=model.prompt_version, scoring_version=model.scoring_version,
            model_version=model.model_version,
        )
        session.add(run)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            active = session.scalar(select(AnalysisRun).where(
                AnalysisRun.company_id == company.id, AnalysisRun.agent_type == agent_type,
                AnalysisRun.status.in_(ACTIVE_STATUSES),
            ))
            if active is None:
                raise
            return active
        return run


def get_run(engine: Engine, run_id: str) -> AnalysisRun | None:
    require_postgres(engine)
    with Session(engine) as session:
        return session.get(AnalysisRun, run_id)


def list_runs(
    engine: Engine, company_id: str, *, limit: int = 20, offset: int = 0,
    agent_type: AgentType | None = None,
) -> list[AnalysisRun]:
    require_postgres(engine)
    if not 1 <= limit <= 100 or offset < 0:
        raise ValueError("Invalid history pagination.")
    statement = select(AnalysisRun).where(AnalysisRun.company_id == company_id)
    if agent_type is not None:
        statement = statement.where(AnalysisRun.agent_type == AgentType(agent_type))
    statement = statement.order_by(AnalysisRun.created_at.desc(), AnalysisRun.id.desc())
    with Session(engine) as session:
        return list(session.scalars(statement.limit(limit).offset(offset)))


def owned_run(
    session: Session, run_id: str, owner: str, generation: int, now: datetime,
) -> AnalysisRun:
    """Hold this row lock only for a short publication transaction."""
    run = session.scalar(select(AnalysisRun).where(AnalysisRun.id == run_id).with_for_update())
    if (run is None or run.status != "running" or run.lease_owner != owner
            or run.lease_generation != generation or run.lease_expires_at is None
            or run.lease_expires_at <= now):
        raise AnalysisError(ErrorCode.LEASE_LOST)
    return run


def publish_terminal(
    engine: Engine, run_id: str, owner: str, generation: int, *,
    result: AgentResult | None = None, error: SafeError | None = None,
    now: datetime | None = None,
) -> AnalysisRun:
    """A lease owner may finalize once; reruns always create new records."""
    require_postgres(engine)
    if (result is None) == (error is None):
        raise ValueError("Publish exactly one validated result or safe error.")
    now = now or utcnow()
    with Session(engine, expire_on_commit=False) as session, session.begin():
        run = owned_run(session, run_id, owner, generation, now)
        if result is not None:
            # Revalidate even a caller-created model_copy/model_construct instance.
            result = AgentResult.model_validate(result.model_dump(mode="json"))
            if (result.run_id != run.id or result.agent_type != run.agent_type
                    or result.company.model_dump(mode="json") != run.company_snapshot
                    or result.as_of != run.as_of):
                raise AnalysisError(ErrorCode.INVALID_OUTPUT)
            run.result = result.model_dump(mode="json")
            run.status = result.status.value
        else:
            error = SafeError.model_validate(error.model_dump(mode="json"))
            run.error = error.model_dump(mode="json")
            run.status = "failed"
        run.finished_at = now
        run.lease_owner = None
        run.lease_expires_at = None
        return run
