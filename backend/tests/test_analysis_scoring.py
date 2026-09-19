"""C02 deterministic scores, coverage thresholds, gates and confidence."""

import unittest

from pydantic import ValidationError

from app.analysis.contracts import AnalysisError, Confidence, ModelParameterScore, ParameterScore, ResultStatus
from app.analysis.scoring import (
    Dimension, EvidenceQuality, FUNDAMENTAL_DIMENSIONS, TECHNICAL_DIMENSIONS,
    assess_confidence, normalized_weighted_average, score_fixed_dimensions,
)


class AnalysisScoringTests(unittest.TestCase):
    def findings(self, scores, dimensions=TECHNICAL_DIMENSIONS):
        return tuple(ModelParameterScore(
            key=dimension.key, score=score, explanation="Synthetic finding",
            evidence_ids=("e1",) if score is not None else (),
        ) for dimension, score in zip(dimensions, scores))

    def score(self, scores, **options):
        dimensions = options.pop("dimensions", TECHNICAL_DIMENSIONS)
        gates = options.pop("mandatory_gates", {"image_delivered": True, "valid_indicators": True})
        return score_fixed_dimensions(self.findings(scores, dimensions), dimensions=dimensions,
                                      known_evidence_ids={"e1"}, mandatory_gates=gates, **options)

    def parameter(self, key="event", score=6, weight=1, evidence_ids=("e1",)):
        return ParameterScore(key=key, name="Synthetic event", score=score, weight=weight,
                              explanation="Synthetic finding", evidence_ids=evidence_ids)

    def test_c02_01_complete_technical(self):
        result = self.score([8, 6, 4, 7])
        self.assertEqual(result.final_score, 6.3)
        self.assertEqual(result.coverage, 100)
        self.assertEqual(result.status, ResultStatus.COMPLETED)
        self.assertEqual(result.confidence, Confidence.HIGH)

    def test_c02_02_partial_technical_preserves_null(self):
        for scores in ([8, 6, 4, None], [8, 6, 4]):
            result = self.score(scores)
            self.assertEqual(result.final_score, 6.1)
            self.assertEqual(result.coverage, 80)
            self.assertIsNone(result.parameters[-1].score)
            self.assertEqual(result.confidence, Confidence.MEDIUM)

    def test_c02_03_exact_threshold_and_zero(self):
        for supported, missing, eligible in ((70, 30, True), (69.999999, 30.000001, False), (0, 100, False)):
            dimensions = (Dimension(key="supported", name="Supported", weight=supported),
                          Dimension(key="missing", name="Missing", weight=missing))
            result = self.score([6, None], dimensions=dimensions)
            self.assertEqual(result.status == ResultStatus.COMPLETED, eligible)
            self.assertEqual(result.final_score, 6 if eligible else None)
            self.assertAlmostEqual(result.coverage, supported)
        result = self.score([None] * 4)
        self.assertIsNone(result.final_score)
        self.assertEqual(result.coverage, 0)
        self.assertEqual(result.confidence, Confidence.LOW)
        generic = normalized_weighted_average([self.parameter(score=None, evidence_ids=())], known_evidence_ids=set())
        self.assertIsNone(generic.final_score)
        self.assertEqual(generic.coverage, 0)

    def test_c02_04_mandatory_gate(self):
        result = self.score([8, 6, 4, 7], mandatory_gates={"chart image delivered": False})
        self.assertIsNone(result.final_score)
        self.assertEqual(result.coverage, 100)
        self.assertEqual(result.status, ResultStatus.INSUFFICIENT_DATA)
        self.assertIn("Required evidence gate failed: chart image delivered.", result.limitations)
        self.assertNotEqual(result.confidence, Confidence.HIGH)
        with self.assertRaises(AnalysisError):
            self.score([8, 6, 4, 7], mandatory_gates={"image_delivered": "true"})

    def test_c02_05_extremes_order_and_half_up(self):
        for value in (0, 10):
            self.assertEqual(self.score([value] * 4).final_score, value)
        findings = self.findings([8, 6, 4, 7])
        result = score_fixed_dimensions(tuple(reversed(findings)), dimensions=TECHNICAL_DIMENSIONS,
                                        known_evidence_ids={"e1"}, mandatory_gates={})
        self.assertEqual(result.final_score, 6.3)
        self.assertEqual([item.key for item in result.parameters], [item.key for item in TECHNICAL_DIMENSIONS])
        for value, expected in ((6.25, 6.3), (6.15, 6.2), (0.05, 0.1), (9.95, 10)):
            aggregate = normalized_weighted_average([self.parameter(score=value)], known_evidence_ids={"e1"})
            self.assertEqual(aggregate.final_score, expected)
        # Rounding individual scores first would incorrectly give 6.3 here.
        aggregate = normalized_weighted_average([
            self.parameter(key="a", score=6.24, weight=1),
            self.parameter(key="b", score=6.25, weight=1),
        ], known_evidence_ids={"e1"})
        self.assertEqual(aggregate.final_score, 6.2)
        self.assertEqual(sum(item.weight for item in FUNDAMENTAL_DIMENSIONS), 100)
        self.assertEqual(self.score([6] * 6, dimensions=FUNDAMENTAL_DIMENSIONS).final_score, 6)

    def test_c02_06_invalid_aggregation_and_server_owned_weights(self):
        for value in (-1, float("nan"), float("inf"), True, "10"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                self.parameter(weight=value)
        invalid_inputs = [
            [], [self.parameter(weight=0)], [self.parameter(), self.parameter()],
            [self.parameter(evidence_ids=())], [self.parameter(evidence_ids=("unknown",))],
            [self.parameter(score=None, evidence_ids=("unknown",))],
        ]
        for parameters in invalid_inputs:
            with self.subTest(parameters=parameters), self.assertRaises(AnalysisError):
                normalized_weighted_average(parameters, known_evidence_ids={"e1"})
        with self.assertRaises(ValidationError):
            normalized_weighted_average([self.parameter().model_copy(update={"weight": -1})], known_evidence_ids={"e1"})
        findings = self.findings([8, 6, 4, 7])
        invalid_configs = [(), (TECHNICAL_DIMENSIONS[0], TECHNICAL_DIMENSIONS[0])]
        for dimensions in invalid_configs:
            with self.assertRaises(AnalysisError):
                score_fixed_dimensions(findings, dimensions=dimensions, known_evidence_ids={"e1"}, mandatory_gates={})
        invalid_findings = [
            (*findings, findings[0]),
            (ModelParameterScore(key="unknown", score=5, explanation="Synthetic", evidence_ids=("e1",)),),
            (self.parameter(key="price_structure", weight=999),),
        ]
        for inputs in invalid_findings:
            with self.assertRaises(AnalysisError):
                score_fixed_dimensions(inputs, dimensions=TECHNICAL_DIMENSIONS,
                                       known_evidence_ids={"e1"}, mandatory_gates={})
        result = score_fixed_dimensions((self.parameter(key="price_structure", weight=30),),
                                        dimensions=TECHNICAL_DIMENSIONS, known_evidence_ids={"e1"}, mandatory_gates={})
        self.assertEqual(result.parameters[0].name, TECHNICAL_DIMENSIONS[0].name)
        self.assertEqual(result.parameters[0].weight, 30)
        self.assertIsNone(result.final_score)

    def test_c02_07_evidence_quality_changes_confidence_not_direction(self):
        baseline = self.score([8, 6, 4, 7])
        for quality in (EvidenceQuality(stale=True), EvidenceQuality(consistent_sources=False),
                        EvidenceQuality(ambiguous=True)):
            result = self.score([8, 6, 4, 7], evidence_quality=quality)
            self.assertEqual(result.final_score, baseline.final_score)
            self.assertEqual(result.confidence, Confidence.LOW)
            self.assertTrue(result.limitations)
        result = self.score([8, 6, 4, 7], evidence_quality=EvidenceQuality(required_evidence_complete=False))
        self.assertEqual(result.confidence, Confidence.MEDIUM)
        self.assertIn("Required evidence is incomplete.", result.limitations)
        result = self.score([8, 6, 4, 7], confidence_cap=Confidence.MEDIUM)
        self.assertEqual(result.confidence, Confidence.MEDIUM)
        self.assertIn("Domain evidence rules reduce confidence.", result.limitations)
        # A domain cap can never raise the shared evidence assessment.
        result = self.score([8, 6, 4, 7], evidence_quality=EvidenceQuality(stale=True), confidence_cap=Confidence.HIGH)
        self.assertEqual(result.confidence, Confidence.LOW)
        confidence, _ = assess_confidence(coverage=70, quality=EvidenceQuality(), confidence_cap=Confidence.MEDIUM)
        self.assertEqual(confidence, Confidence.MEDIUM)


if __name__ == "__main__":
    unittest.main()
