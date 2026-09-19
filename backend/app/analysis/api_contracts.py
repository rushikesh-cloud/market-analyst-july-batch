"""Public analysis responses intentionally omit provider and filesystem internals."""

from .contracts import (
    AgentResult, AgentType, CompanySnapshot, Contract, RunStatus, SafeError, UTCDateTime,
)
from .models import AnalysisRun


class StartRun(Contract):
    agent_type: AgentType


class RunResponse(Contract):
    id: str
    company_id: str
    company: CompanySnapshot
    agent_type: AgentType
    status: RunStatus
    created_at: UTCDateTime
    started_at: UTCDateTime | None
    finished_at: UTCDateTime | None
    as_of: UTCDateTime | None
    progress: dict[str, str]
    result: AgentResult | None
    error: SafeError | None


class RunHistory(Contract):
    items: tuple[RunResponse, ...]
    limit: int
    offset: int


class AgentAvailability(Contract):
    agent_type: AgentType
    available: bool
    error: SafeError | None


class AvailableAgents(Contract):
    items: tuple[AgentAvailability, ...]


_STAGES = {'queued', 'starting', 'researching', 'analyzing', 'validating', 'completed', 'insufficient_data', 'failed'}


def run_response(run: AnalysisRun) -> RunResponse:
    stage = run.progress.get('stage') if isinstance(run.progress, dict) else None
    if not isinstance(stage, str) or stage not in _STAGES:
        stage = 'analyzing' if run.status == 'running' else run.status
    return RunResponse(
        id=run.id, company_id=run.company_id, company=run.company_snapshot,
        agent_type=run.agent_type, status=run.status, created_at=run.created_at,
        started_at=run.started_at, finished_at=run.finished_at, as_of=run.as_of,
        progress={'stage': stage}, result=run.result, error=run.error,
    )
