"""Synthetic contract examples, never registered by production startup."""

from datetime import date, datetime, timedelta, timezone
from typing import Literal

from .contracts import (
    AgentResult, AgentType, AnalysisError, CompanySnapshot, Confidence,
    DataObservation, ErrorCode, EvidenceProvenance, EvidenceReference,
    EvidenceSource, EvidenceType, FailedRunFixture, FinancialMetric,
    FundamentalDetails, NewsCategoryScore, NewsDetails, NewsEvent,
    ParameterScore, ResultStatus, TechnicalDetails, TechnicalObservation,
)

FIXTURE_AS_OF = datetime(2026, 7, 1, 12, tzinfo=timezone.utc)
FIXTURE_COMPANY = CompanySnapshot(
    id="synthetic-company", name="Synthetic Example Limited", ticker="SYNTHETIC.NS"
)

_DIMENSIONS = {
    AgentType.FUNDAMENTAL: (
        ("growth", "Growth and business resilience", 15),
        ("profitability", "Profitability and efficiency", 20),
        ("balance_sheet", "Balance-sheet strength", 20),
        ("cash_generation", "Cash generation and liquidity", 20),
        ("governance", "Governance and reporting quality", 15),
        ("outlook", "Outlook and business risks", 10),
    ),
    AgentType.TECHNICAL: (
        ("price_structure", "Price structure and trend", 30),
        ("macd", "MACD momentum", 25),
        ("rsi", "RSI condition", 25),
        ("volume", "Volume confirmation", 20),
    ),
    AgentType.NEWS: (("event-1", "Synthetic business development", 2),),
}


def result_fixture(
    agent_type: AgentType | str,
    scenario: Literal["completed", "insufficient_data", "partial"] = "completed",
    *,
    run_id: str | None = None,
    company: CompanySnapshot = FIXTURE_COMPANY,
    as_of: datetime = FIXTURE_AS_OF,
) -> AgentResult:
    """Produce deterministic examples with representative typed details and nulls."""
    agent = AgentType(agent_type)
    if scenario not in ("completed", "insufficient_data", "partial"):
        raise ValueError("Unknown fixture scenario.")
    run_id = run_id or f"synthetic-{agent}-{scenario}"
    insufficient = scenario == "insufficient_data"
    partial = scenario == "partial"
    evidence_id = "evidence-1"
    artifact_id = "chart-1" if agent == AgentType.TECHNICAL else None
    source = EvidenceSource(
        title="Synthetic evidence; not a real financial fact",
        document_id="synthetic-report" if agent == AgentType.FUNDAMENTAL else None,
        chunk_id="synthetic-chunk" if agent == AgentType.FUNDAMENTAL else None,
        page=1 if agent == AgentType.FUNDAMENTAL else None,
        fiscal_year="2025-26" if agent == AgentType.FUNDAMENTAL else None,
        url="https://example.invalid/synthetic-news" if agent == AgentType.NEWS else None,
        publisher="Synthetic publisher" if agent == AgentType.NEWS else None,
        published_at=as_of - timedelta(days=2) if agent == AgentType.NEWS else None,
        date_precision="timestamp" if agent == AgentType.NEWS else "unknown",
        artifact_id=artifact_id,
    )
    evidence = () if insufficient else (EvidenceReference(
        id=evidence_id, run_id=run_id,
        type={AgentType.FUNDAMENTAL: EvidenceType.REPORT_CHUNK,
              AgentType.TECHNICAL: EvidenceType.CHART, AgentType.NEWS: EvidenceType.ARTICLE}[agent],
        source=source, excerpt="Synthetic supporting observation for contract validation.",
        observation=DataObservation(key="synthetic", value=6, unit=None,
                                    observed_at=as_of, description="Synthetic data")
        if agent == AgentType.TECHNICAL else None,
        provenance=EvidenceProvenance(provider="synthetic", retrieved_at=as_of,
                                      tool="fixture", source_snapshot_id="snapshot-1"),
    ),)
    dimensions = list(_DIMENSIONS[agent])
    if partial and agent == AgentType.NEWS:
        dimensions.append(("event-2", "Unassessed synthetic event", 0.5))
    parameters = tuple(ParameterScore(
        key=key, name=name, weight=weight,
        score=None if insufficient or (partial and index == len(dimensions) - 1) else 6,
        explanation="Synthetic fixture finding; not investment research.",
        evidence_ids=() if insufficient or (partial and index == len(dimensions) - 1)
        else (evidence_id,),
    ) for index, (key, name, weight) in enumerate(dimensions))
    ids = () if insufficient else (evidence_id,)
    if agent == AgentType.FUNDAMENTAL:
        details = FundamentalDetails(
            report_id=None if insufficient else "synthetic-report",
            fiscal_year=None if insufficient else "2025-26",
            basis="unknown" if insufficient else "consolidated",
            sector_profile=None if insufficient else "operating_company",
            sector_evidence_ids=ids,
            metrics=(FinancialMetric(key="revenue", label="Synthetic revenue", value=None if insufficient else 100,
                                     currency="INR", scale="million", fiscal_period="2025-26",
                                     basis="consolidated", origin="reported", evidence_ids=ids),),
            warnings=(),
        )
    elif agent == AgentType.TECHNICAL:
        details = TechnicalDetails(
            chart_artifact_id=None if insufficient else "chart-1",
            data_artifact_id=None if insufficient else "data-1",
            data_start=None if insufficient else date(2025, 7, 1),
            data_end=None if insufficient else as_of.date(),
            session_count=0 if insufficient else 250,
            adjustment=None if insufficient else "Synthetic consistently adjusted OHLC",
            image_delivered=not insufficient,
            observations=(TechnicalObservation(key="rsi", value=None if insufficient else 55,
                                               explanation="Synthetic RSI observation", evidence_ids=ids),),
            signal_agreement=None if insufficient else "Synthetic indicators agree.",
        )
    else:
        details = NewsDetails(
            window_start=as_of - timedelta(days=30), window_end=as_of,
            events=tuple(NewsEvent(
                key=parameter.key, title=parameter.name, category="business_developments",
                sentiment=parameter.score, materiality=1, factual_status="confirmed",
                source_class="attributable_reporting", explanation=parameter.explanation,
                uncertainty=None, evidence_ids=ids, event_date=None if insufficient else as_of.date(),
                weight=parameter.weight, eligible=not insufficient,
            ) for parameter in parameters),
            category_scores=tuple(NewsCategoryScore(
                category=category, score=6 if category == "business_developments" and not insufficient else None
            ) for category in ("financial_results", "business_developments", "governance_regulatory")),
            retained_article_count=0 if insufficient else len(parameters),
            coverage_description="Coverage of synthetic retained eligible event weight only.",
        )
    return AgentResult(
        run_id=run_id, agent_type=agent,
        status=ResultStatus.INSUFFICIENT_DATA if insufficient else ResultStatus.COMPLETED,
        company=company, as_of=as_of, evidence_dates=() if insufficient else (as_of.date(),),
        horizon="Report period" if agent == AgentType.FUNDAMENTAL else "2–8 weeks",
        summary="Synthetic fixture only; no real financial facts.", parameters=parameters,
        final_score=None if insufficient else 6,
        confidence=Confidence.LOW if insufficient else Confidence.MEDIUM if partial else Confidence.HIGH,
        coverage=0 if insufficient else 90 if partial and agent == AgentType.FUNDAMENTAL else 80 if partial else 100,
        strengths=() if insufficient else ("Synthetic supported strength",),
        risks=(), limitations=("Synthetic data only",) + (("Some evidence is missing",) if partial or insufficient else ()),
        evidence=evidence, details=details,
    )


def failed_run_fixture(agent_type: AgentType | str) -> FailedRunFixture:
    agent = AgentType(agent_type)
    return FailedRunFixture(
        run_id=f"synthetic-{agent}-failed", agent_type=agent, company=FIXTURE_COMPANY,
        as_of=FIXTURE_AS_OF, error=AnalysisError(ErrorCode.PROVIDER_UNAVAILABLE).as_safe_error(),
    )


def all_fixtures() -> tuple[AgentResult | FailedRunFixture, ...]:
    return tuple(
        fixture for agent in AgentType
        for fixture in (*(result_fixture(agent, scenario)
                          for scenario in ("completed", "insufficient_data", "partial")),
                        failed_run_fixture(agent))
    )
