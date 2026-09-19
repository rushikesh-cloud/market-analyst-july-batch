"""Versioned analysis contracts; all identity and arithmetic are server-owned.

Model output classes deliberately omit identity, dates, configured weights and final
scores. Adapters combine validated findings with trusted context and scoring services.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any, Literal, Mapping, Protocol

from pydantic import (
    AfterValidator, AwareDatetime, BaseModel, BeforeValidator, ConfigDict, Field,
    model_validator,
)

SCHEMA_VERSION = "1.0"


def _number(value: Any) -> Any:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValueError("Expected a finite number, not a boolean or numeric string.")
    return value


def _utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc)


FiniteNumber = Annotated[float, BeforeValidator(_number), Field(allow_inf_nan=False)]
Score = Annotated[FiniteNumber, Field(ge=0, le=10)]
Weight = Annotated[FiniteNumber, Field(ge=0)]
Percentage = Annotated[FiniteNumber, Field(ge=0, le=100)]
UTCDateTime = Annotated[AwareDatetime, AfterValidator(_utc)]
Identifier = Annotated[str, Field(min_length=1, max_length=200)]
Text = Annotated[str, Field(min_length=1, max_length=12000)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class AgentType(StrEnum):
    FUNDAMENTAL = "fundamental"
    TECHNICAL = "technical"
    NEWS = "news"


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    INSUFFICIENT_DATA = "insufficient_data"
    FAILED = "failed"


class ResultStatus(StrEnum):
    COMPLETED = "completed"
    INSUFFICIENT_DATA = "insufficient_data"


class Confidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ErrorCode(StrEnum):
    INVALID_AGENT = "invalid_agent"
    AGENT_UNAVAILABLE = "agent_unavailable"
    CONFIGURATION_ERROR = "configuration_error"
    POSTGRESQL_REQUIRED = "postgresql_required"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    UNSUPPORTED_IMAGE_INPUT = "unsupported_image_input"
    INVALID_OUTPUT = "invalid_output"
    BUDGET_EXHAUSTED = "budget_exhausted"
    DEADLINE_EXCEEDED = "deadline_exceeded"
    ATTEMPTS_EXHAUSTED = "attempts_exhausted"
    LEASE_LOST = "lease_lost"
    SOURCE_CHANGED = "source_changed"
    ARTIFACT_UNAVAILABLE = "artifact_unavailable"
    ARTIFACT_CORRUPT = "artifact_corrupt"
    TICKER_CORRECTION_REQUIRED = "ticker_correction_required"
    INTERNAL_ERROR = "internal_error"


_SAFE_MESSAGES = {
    ErrorCode.INVALID_AGENT: "Choose a supported analysis agent.",
    ErrorCode.AGENT_UNAVAILABLE: "This analysis agent is not installed.",
    ErrorCode.CONFIGURATION_ERROR: "Analysis configuration is unavailable.",
    ErrorCode.POSTGRESQL_REQUIRED: "Analysis requires PostgreSQL.",
    ErrorCode.PROVIDER_UNAVAILABLE: "The analysis provider is unavailable. Try again later.",
    ErrorCode.UNSUPPORTED_IMAGE_INPUT: "The configured model does not support chart images.",
    ErrorCode.INVALID_OUTPUT: "The analysis output could not be validated.",
    ErrorCode.BUDGET_EXHAUSTED: "The analysis execution limit was reached.",
    ErrorCode.DEADLINE_EXCEEDED: "The analysis execution deadline was reached.",
    ErrorCode.ATTEMPTS_EXHAUSTED: "The analysis attempt limit was reached.",
    ErrorCode.LEASE_LOST: "The analysis execution lease was lost.",
    ErrorCode.SOURCE_CHANGED: "The source changed during analysis. Start a new run.",
    ErrorCode.ARTIFACT_UNAVAILABLE: "The analysis artifact is unavailable.",
    ErrorCode.ARTIFACT_CORRUPT: "The analysis artifact failed integrity validation.",
    ErrorCode.TICKER_CORRECTION_REQUIRED: "Save a canonical NSE ticker before analysis.",
    ErrorCode.INTERNAL_ERROR: "Analysis could not complete. Try again later.",
}


class SafeError(Contract):
    code: ErrorCode
    message: Text

    @model_validator(mode="after")
    def safe_message(self):
        if self.message != _SAFE_MESSAGES[self.code]:
            raise ValueError("Error messages must use the safe error catalog.")
        return self


class AnalysisError(Exception):
    """Never wrap raw provider text in an API-visible error message."""

    def __init__(self, code: ErrorCode):
        self.code = ErrorCode(code)
        self.message = _SAFE_MESSAGES[self.code]
        super().__init__(self.message)

    def as_safe_error(self) -> SafeError:
        return SafeError(code=self.code, message=self.message)


class CompanySnapshot(Contract):
    id: Identifier
    name: Annotated[str, Field(min_length=1, max_length=200)]
    ticker: Annotated[str, Field(min_length=1, max_length=40)]


class ModelConfiguration(Contract):
    deployment: Identifier
    api_version: Identifier
    prompt_version: Identifier = "1.0"
    scoring_version: Identifier = "1.0"
    model_version: Identifier | None = None


class AnalysisContext(Contract):
    """Runtime-only context, built from a claimed run, never model/tool arguments."""

    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)
    run_id: Identifier
    agent_type: AgentType
    company: CompanySnapshot
    as_of: UTCDateTime
    model: ModelConfiguration
    providers: Mapping[str, Any]
    store: Any
    budget: Any


class ParameterScore(Contract):
    key: Identifier
    name: Text
    weight: Weight
    score: Score | None
    explanation: Text
    evidence_ids: tuple[Identifier, ...]


class ModelParameterScore(Contract):
    key: Identifier
    score: Score | None
    explanation: Text
    evidence_ids: tuple[Identifier, ...]


class EvidenceType(StrEnum):
    REPORT_CHUNK = "report_chunk"
    ARTICLE = "article"
    DATA_OBSERVATION = "data_observation"
    CHART = "chart"


class EvidenceSource(Contract):
    title: Text
    document_id: Identifier | None = None
    chunk_id: Identifier | None = None
    page: Annotated[int, Field(strict=True, ge=1)] | None = None
    fiscal_year: Identifier | None = None
    url: Annotated[str, Field(max_length=4000)] | None = None
    publisher: Identifier | None = None
    published_at: UTCDateTime | None = None
    publication_date: date | None = None
    date_precision: Literal["timestamp", "date", "unknown"] = "unknown"
    artifact_id: Identifier | None = None


class EvidenceProvenance(Contract):
    provider: Identifier
    retrieved_at: UTCDateTime
    tool: Identifier
    source_snapshot_id: Identifier | None = None


class DataObservation(Contract):
    key: Identifier
    value: FiniteNumber | None
    unit: Identifier | None
    observed_at: UTCDateTime | None
    description: Text


class EvidenceReference(Contract):
    id: Identifier
    run_id: Identifier
    type: EvidenceType
    source: EvidenceSource
    excerpt: Annotated[str, Field(max_length=4000)] | None
    observation: DataObservation | None
    provenance: EvidenceProvenance

    @model_validator(mode="after")
    def supporting_content(self):
        if not self.excerpt and self.observation is None:
            raise ValueError("Evidence requires a bounded excerpt or data observation.")
        return self


class FinancialMetric(Contract):
    key: Identifier
    label: Text
    value: FiniteNumber | None
    currency: Identifier | None
    scale: Identifier
    fiscal_period: Identifier
    basis: Literal["consolidated", "standalone", "unknown"]
    origin: Literal["reported", "derived"]
    evidence_ids: tuple[Identifier, ...]


SectorProfile = Literal[
    "operating_company", "bank", "nbfc", "life_insurer", "general_insurer", "ambiguous"
]


class FundamentalDetails(Contract):
    kind: Literal["fundamental"] = "fundamental"
    report_id: Identifier | None
    fiscal_year: Identifier | None
    basis: Literal["consolidated", "standalone", "unknown"]
    sector_profile: SectorProfile | None
    sector_evidence_ids: tuple[Identifier, ...]
    metrics: tuple[FinancialMetric, ...]
    warnings: tuple[Text, ...]


class TechnicalObservation(Contract):
    key: Identifier
    value: FiniteNumber | None
    explanation: Text
    evidence_ids: tuple[Identifier, ...]


class TechnicalDetails(Contract):
    kind: Literal["technical"] = "technical"
    chart_artifact_id: Identifier | None
    data_artifact_id: Identifier | None
    data_start: date | None
    data_end: date | None
    session_count: Annotated[int, Field(strict=True, ge=0)]
    adjustment: Text | None
    image_delivered: bool
    observations: tuple[TechnicalObservation, ...]
    signal_agreement: Text | None


NewsCategory = Literal["financial_results", "business_developments", "governance_regulatory"]
SourceClass = Literal["official", "attributable_reporting", "commentary", "uncorroborated"]


class ModelNewsEvent(Contract):
    key: Identifier
    title: Text
    category: NewsCategory
    sentiment: Score | None
    materiality: Annotated[int, Field(strict=True, ge=1, le=3)]
    factual_status: Literal["confirmed", "commentary", "allegation", "disputed"]
    source_class: SourceClass
    explanation: Text
    uncertainty: Text | None
    evidence_ids: tuple[Identifier, ...]


class NewsEvent(ModelNewsEvent):
    event_date: date | None
    weight: Weight
    eligible: bool


class NewsCategoryScore(Contract):
    category: NewsCategory
    score: Score | None


class NewsDetails(Contract):
    kind: Literal["news"] = "news"
    window_start: UTCDateTime
    window_end: UTCDateTime
    events: tuple[NewsEvent, ...]
    category_scores: tuple[NewsCategoryScore, ...]
    retained_article_count: Annotated[int, Field(strict=True, ge=0)]
    coverage_description: Text


AgentDetails = Annotated[
    FundamentalDetails | TechnicalDetails | NewsDetails, Field(discriminator="kind")
]


class AgentResult(Contract):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    run_id: Identifier
    agent_type: AgentType
    status: ResultStatus
    company: CompanySnapshot
    as_of: UTCDateTime
    evidence_dates: tuple[date, ...]
    horizon: Text
    summary: Text
    parameters: tuple[ParameterScore, ...]
    final_score: Score | None
    confidence: Confidence
    coverage: Percentage
    strengths: tuple[Text, ...]
    risks: tuple[Text, ...]
    limitations: tuple[Text, ...]
    evidence: tuple[EvidenceReference, ...]
    details: AgentDetails

    @model_validator(mode="after")
    def coherent_result(self):
        if self.details.kind != self.agent_type.value:
            raise ValueError("Agent type does not match the detail variant.")
        keys = [item.key for item in self.parameters]
        if len(keys) != len(set(keys)):
            raise ValueError("Parameter keys must be unique.")
        if (self.status == ResultStatus.COMPLETED) != (self.final_score is not None):
            raise ValueError("Only completed results have a final score.")
        ids = [item.id for item in self.evidence]
        if len(ids) != len(set(ids)):
            raise ValueError("Evidence IDs must be unique.")
        if any(item.run_id != self.run_id for item in self.evidence):
            raise ValueError("Evidence must belong to this run.")
        unknown = _citation_ids(self.model_dump()) - set(ids)
        if unknown:
            raise ValueError("Result cites evidence outside its run-local ledger.")
        return self


def _citation_ids(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key.endswith("evidence_ids"):
                found.update(item)
            else:
                found.update(_citation_ids(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            found.update(_citation_ids(item))
    return found


class ModelFindings(Contract):
    summary: Text
    parameters: tuple[ModelParameterScore, ...]
    strengths: tuple[Text, ...]
    risks: tuple[Text, ...]
    limitations: tuple[Text, ...]

    @model_validator(mode="after")
    def unique_keys(self):
        keys = [item.key for item in self.parameters]
        if len(keys) != len(set(keys)):
            raise ValueError("Parameter keys must be unique.")
        return self


class FundamentalModelOutput(ModelFindings):
    sector_profile: SectorProfile | None
    sector_evidence_ids: tuple[Identifier, ...]
    metrics: tuple[FinancialMetric, ...]


class TechnicalModelOutput(ModelFindings):
    observations: tuple[TechnicalObservation, ...]
    signal_agreement: Text | None


class NewsModelOutput(ModelFindings):
    events: tuple[ModelNewsEvent, ...]


MODEL_OUTPUT_SCHEMAS = {
    AgentType.FUNDAMENTAL: FundamentalModelOutput,
    AgentType.TECHNICAL: TechnicalModelOutput,
    AgentType.NEWS: NewsModelOutput,
}


class FailedRunFixture(Contract):
    """Failure is a run state, never a fabricated AgentResult."""

    run_id: Identifier
    agent_type: AgentType
    company: CompanySnapshot
    status: Literal["failed"] = "failed"
    as_of: UTCDateTime
    result: None = None
    error: SafeError


class AgentAdapter(Protocol):
    def run(self, context: AnalysisContext) -> AgentResult: ...


def validate_result(
    result: AgentResult,
    context: AnalysisContext,
    *,
    known_evidence_ids: set[str],
    known_artifact_ids: set[str],
) -> AgentResult:
    """Validate publication against trusted context and the registered run ledger."""
    result = AgentResult.model_validate(result.model_dump())
    if (
        result.run_id != context.run_id
        or result.agent_type != context.agent_type
        or result.company != context.company
        or result.as_of != context.as_of
        or not {item.id for item in result.evidence} <= known_evidence_ids
    ):
        raise AnalysisError(ErrorCode.INVALID_OUTPUT)
    artifact_ids = {
        item.source.artifact_id for item in result.evidence
        if item.source.artifact_id is not None
    }
    if isinstance(result.details, TechnicalDetails):
        artifact_ids.update(
            item for item in (result.details.chart_artifact_id, result.details.data_artifact_id)
            if item is not None
        )
    if not artifact_ids <= known_artifact_ids:
        raise AnalysisError(ErrorCode.INVALID_OUTPUT)
    return result
