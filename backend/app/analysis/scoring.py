"""Deterministic arithmetic and evidence-quality assessment shared by agents.

Fixed dimensions use configured weights; news supplies retained eligible events to
the generic aggregation utility and owns its different denominator rules.
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import Mapping, Sequence

from .contracts import (
    AnalysisError, Confidence, Contract, ErrorCode, Identifier, ModelParameterScore,
    ParameterScore, Percentage, ResultStatus, Score, Text, Weight,
)


class Dimension(Contract):
    key: Identifier
    name: Text
    weight: Weight


FUNDAMENTAL_DIMENSIONS = (
    Dimension(key="growth", name="Growth and business resilience", weight=15),
    Dimension(key="profitability", name="Profitability and efficiency", weight=20),
    Dimension(key="balance_sheet", name="Balance-sheet strength", weight=20),
    Dimension(key="cash_generation", name="Cash generation and liquidity", weight=20),
    Dimension(key="governance", name="Governance and reporting quality", weight=15),
    Dimension(key="outlook", name="Outlook and business risks", weight=10),
)
TECHNICAL_DIMENSIONS = (
    Dimension(key="price_structure", name="Price structure and trend", weight=30),
    Dimension(key="macd", name="MACD momentum", weight=25),
    Dimension(key="rsi", name="RSI condition", weight=25),
    Dimension(key="volume", name="Volume confirmation", weight=20),
)


class WeightedAggregation(Contract):
    final_score: Score | None
    coverage: Percentage
    supported_weight: Weight
    total_weight: Weight


class EvidenceQuality(Contract):
    required_evidence_complete: bool = True
    consistent_sources: bool = True
    stale: bool = False
    ambiguous: bool = False


class ScoringOutcome(Contract):
    status: ResultStatus
    parameters: tuple[ParameterScore, ...]
    final_score: Score | None
    coverage: Percentage
    confidence: Confidence
    limitations: tuple[Text, ...]


def _aggregate(
    parameters: Sequence[ParameterScore], known_evidence_ids: set[str]
) -> tuple[Decimal | None, Decimal, Decimal, Decimal]:
    if not parameters:
        raise AnalysisError(ErrorCode.INVALID_OUTPUT)
    seen: set[str] = set()
    total = Decimal(0)
    supported = Decimal(0)
    numerator = Decimal(0)
    for parameter in parameters:
        # Revalidate copies and any duck-typed caller before calculating.
        parameter = ParameterScore.model_validate(parameter.model_dump())
        if parameter.key in seen:
            raise AnalysisError(ErrorCode.INVALID_OUTPUT)
        seen.add(parameter.key)
        if not set(parameter.evidence_ids) <= known_evidence_ids:
            raise AnalysisError(ErrorCode.INVALID_OUTPUT)
        weight = Decimal(str(parameter.weight))
        total += weight
        if parameter.score is not None:
            if not parameter.evidence_ids:
                raise AnalysisError(ErrorCode.INVALID_OUTPUT)
            supported += weight
            numerator += Decimal(str(parameter.score)) * weight
    if total == 0:
        raise AnalysisError(ErrorCode.INVALID_OUTPUT)
    coverage = 100 * supported / total
    score = numerator / supported if supported else None
    return score, coverage, supported, total


def _rounded(score: Decimal | None) -> float | None:
    return float(score.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)) if score is not None else None


def normalized_weighted_average(
    parameters: Sequence[ParameterScore], *, known_evidence_ids: set[str]
) -> WeightedAggregation:
    """Aggregate supplied eligible items; callers own inclusion and minimum gates.

    An unassessed retained item has a null score and stays in the denominator.
    Unknown or unsupported citations invalidate the aggregation rather than turning
    a hallucinated finding into a number. The average is rounded once, half-up.
    """
    score, coverage, supported, total = _aggregate(parameters, known_evidence_ids)
    return WeightedAggregation(
        final_score=_rounded(score), coverage=float(coverage),
        supported_weight=float(supported), total_weight=float(total),
    )


def assess_confidence(
    *, coverage: Decimal | float, quality: EvidenceQuality,
    confidence_cap: Confidence | None = None,
) -> tuple[Confidence, tuple[str, ...]]:
    """Assess evidence quality independently of the numerical score's direction."""
    limitations: list[str] = []
    if coverage < 100:
        limitations.append("Some configured evidence is missing.")
    if not quality.required_evidence_complete:
        limitations.append("Required evidence is incomplete.")
    if not quality.consistent_sources:
        limitations.append("Sources contain material conflicting evidence.")
    if quality.stale:
        limitations.append("Evidence is stale for this assessment.")
    if quality.ambiguous:
        limitations.append("Evidence contains material ambiguity.")
    if coverage < 70 or not quality.consistent_sources or quality.stale or quality.ambiguous:
        confidence = Confidence.LOW
    elif coverage == 100 and quality.required_evidence_complete:
        confidence = Confidence.HIGH
    else:
        confidence = Confidence.MEDIUM
    order = (Confidence.LOW, Confidence.MEDIUM, Confidence.HIGH)
    if confidence_cap is not None and order.index(confidence_cap) < order.index(confidence):
        confidence = confidence_cap
        limitations.append("Domain evidence rules reduce confidence.")
    return confidence, tuple(limitations)


def score_fixed_dimensions(
    findings: Sequence[ModelParameterScore | ParameterScore],
    *,
    dimensions: Sequence[Dimension],
    known_evidence_ids: set[str],
    mandatory_gates: Mapping[str, bool],
    evidence_quality: EvidenceQuality = EvidenceQuality(),
    confidence_cap: Confidence | None = None,
) -> ScoringOutcome:
    """Bind findings to server dimensions, then apply unrounded coverage and gates."""
    if not dimensions:
        raise AnalysisError(ErrorCode.INVALID_OUTPUT)
    configured: dict[str, Dimension] = {}
    for dimension in dimensions:
        dimension = Dimension.model_validate(dimension.model_dump())
        if dimension.key in configured:
            raise AnalysisError(ErrorCode.INVALID_OUTPUT)
        configured[dimension.key] = dimension
    provided: dict[str, ModelParameterScore | ParameterScore] = {}
    for finding in findings:
        finding = type(finding).model_validate(finding.model_dump())
        if finding.key not in configured or finding.key in provided:
            raise AnalysisError(ErrorCode.INVALID_OUTPUT)
        if isinstance(finding, ParameterScore) and finding.weight != configured[finding.key].weight:
            raise AnalysisError(ErrorCode.INVALID_OUTPUT)
        provided[finding.key] = finding
    parameters = tuple(ParameterScore(
        key=dimension.key, name=dimension.name, weight=dimension.weight,
        score=provided[dimension.key].score if dimension.key in provided else None,
        explanation=provided[dimension.key].explanation if dimension.key in provided
        else "No supported finding is available for this parameter.",
        evidence_ids=provided[dimension.key].evidence_ids if dimension.key in provided else (),
    ) for dimension in configured.values())
    score, coverage, _, _ = _aggregate(parameters, known_evidence_ids)
    if any(type(passed) is not bool for passed in mandatory_gates.values()):
        raise AnalysisError(ErrorCode.INVALID_OUTPUT)
    failed_gates = tuple(name for name, passed in mandatory_gates.items() if not passed)
    eligible = coverage >= 70 and not failed_gates and score is not None
    if failed_gates:
        evidence_quality = evidence_quality.model_copy(update={"required_evidence_complete": False})
    confidence, limitations = assess_confidence(
        coverage=coverage, quality=evidence_quality, confidence_cap=confidence_cap,
    )
    limitations += tuple(f"Required evidence gate failed: {name}." for name in failed_gates)
    return ScoringOutcome(
        status=ResultStatus.COMPLETED if eligible else ResultStatus.INSUFFICIENT_DATA,
        parameters=parameters, final_score=_rounded(score) if eligible else None,
        coverage=float(coverage), confidence=confidence, limitations=limitations,
    )
