"""Durable analysis submission and history; no provider calls in request handlers."""

from contextlib import contextmanager

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.companies import Company, CompanyOutput, engine
from app.nse_tickers import is_canonical_nse_ticker
from .api_contracts import (
    AgentAvailability, AvailableAgents, RunHistory, RunResponse, StartRun, run_response,
)
from .artifact_store import ArtifactStore
from .contracts import AgentType, AnalysisError, CompanySnapshot, ErrorCode
from .registry import registry
from .repository import enqueue_run, find_active_run, get_run, list_runs, require_postgres

router = APIRouter(prefix='/api', tags=['analysis'])


@contextmanager
def safe_errors():
    try:
        yield
    except AnalysisError as error:
        status = {
            ErrorCode.INVALID_AGENT: 422,
            ErrorCode.TICKER_CORRECTION_REQUIRED: 409,
            ErrorCode.ARTIFACT_UNAVAILABLE: 404,
            ErrorCode.ARTIFACT_CORRUPT: 404,
        }.get(error.code, 503)
        raise HTTPException(status, error.as_safe_error().model_dump(mode='json')) from None
    except (SQLAlchemyError, ValidationError):
        error = AnalysisError(ErrorCode.CONFIGURATION_ERROR)
        raise HTTPException(503, error.as_safe_error().model_dump(mode='json')) from None


def resolve_configuration(agent_type: AgentType):
    """Resolve settings only; Key Vault and model SDK calls happen in the worker."""
    from app.resources import get_resource_clients

    try:
        clients = get_resource_clients()
        if agent_type == AgentType.NEWS:
            clients.settings.analysis.require_tavily_secret()
        return clients.analysis_model_configuration(agent_type)
    except AnalysisError:
        raise
    except Exception:
        raise AnalysisError(ErrorCode.CONFIGURATION_ERROR) from None


def company_snapshot(company_id: str) -> CompanySnapshot:
    with Session(engine) as session:
        company = session.get(Company, company_id)
        if company is None:
            raise HTTPException(404, 'Company not found.')
        return CompanySnapshot(id=company.id, name=company.name, ticker=company.ticker)


@router.get('/analysis/companies', response_model=list[CompanyOutput])
def analysis_companies():
    """Read-only company choices for analysis, available to both workspace roles."""
    with safe_errors(), Session(engine) as session:
        return session.scalars(select(Company).order_by(Company.name, Company.id)).all()


@router.get('/analysis-agents', response_model=AvailableAgents)
def available_agents():
    items = []
    for agent in AgentType:
        try:
            require_postgres(engine)
            registry.resolve(agent)
            resolve_configuration(agent)
            items.append(AgentAvailability(agent_type=agent, available=True, error=None))
        except AnalysisError as error:
            items.append(AgentAvailability(agent_type=agent, available=False, error=error.as_safe_error()))
    return AvailableAgents(items=tuple(items))


@router.post('/companies/{company_id}/analysis-runs', response_model=RunResponse, status_code=202)
def start_run(company_id: str, payload: StartRun):
    with safe_errors():
        require_postgres(engine)
        company = company_snapshot(company_id)
        if not is_canonical_nse_ticker(company.ticker):
            raise AnalysisError(ErrorCode.TICKER_CORRECTION_REQUIRED)
        active = find_active_run(engine, company.id, payload.agent_type)
        if active is not None:
            return run_response(active)
        registry.resolve(payload.agent_type)
        model = resolve_configuration(payload.agent_type)
        return run_response(enqueue_run(engine, company, payload.agent_type, model))


@router.get('/companies/{company_id}/analysis-runs', response_model=RunHistory)
def company_history(
    company_id: str, limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0), agent_type: AgentType | None = None,
):
    with safe_errors():
        require_postgres(engine)
        company_snapshot(company_id)
        return RunHistory(items=tuple(run_response(row) for row in list_runs(
            engine, company_id, limit=limit, offset=offset, agent_type=agent_type,
        )), limit=limit, offset=offset)


@router.get('/analysis-runs/{run_id}', response_model=RunResponse)
def read_run(run_id: str):
    with safe_errors():
        row = get_run(engine, run_id)
        if row is None:
            raise HTTPException(404, 'Analysis run not found.')
        return run_response(row)


@router.get('/analysis-runs/{run_id}/artifacts/{artifact_id:path}')
def read_artifact(run_id: str, artifact_id: str):
    with safe_errors():
        stored = ArtifactStore(engine, run_id).read(artifact_id)
        return Response(stored.data, media_type=stored.metadata.mime_type, headers={
            'Content-Disposition': f'attachment; filename="{stored.metadata.id}"',
            'X-Content-Type-Options': 'nosniff',
            'Cache-Control': 'private, no-cache',
        })
