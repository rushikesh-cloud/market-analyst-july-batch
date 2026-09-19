"""C01 contract and registry scenarios; all data are explicitly synthetic."""

import json
import unittest
from datetime import datetime, timezone
from decimal import Decimal

from pydantic import ValidationError

from app.analysis.contracts import (
    AgentResult, AgentType, AnalysisContext, AnalysisError, CompanySnapshot,
    ErrorCode, EvidenceReference, FailedRunFixture, ModelConfiguration,
    MODEL_OUTPUT_SCHEMAS, NewsModelOutput, ParameterScore, SafeError,
    validate_result,
)
from app.analysis.fixtures import all_fixtures, failed_run_fixture, result_fixture
from app.analysis.registry import AgentRegistry, registry


class AnalysisContractsTests(unittest.TestCase):
    def context(self, result):
        return AnalysisContext(
            run_id=result.run_id, agent_type=result.agent_type, company=result.company,
            as_of=result.as_of,
            model=ModelConfiguration(deployment="synthetic-model", api_version="synthetic-version"),
            providers={}, store=object(), budget=object(),
        )

    def model_payload(self, agent):
        result = result_fixture(agent)
        common = {
            "summary": result.summary,
            "parameters": [parameter.model_dump(exclude={"name", "weight"}) for parameter in result.parameters],
            "strengths": result.strengths, "risks": result.risks, "limitations": result.limitations,
        }
        if agent == AgentType.FUNDAMENTAL:
            common.update(sector_profile="operating_company", sector_evidence_ids=["evidence-1"], metrics=[])
        elif agent == AgentType.TECHNICAL:
            common.update(observations=[], signal_agreement=None)
        else:
            common.update(events=[event.model_dump(exclude={"event_date", "weight", "eligible"})
                                  for event in result.details.events])
        return common

    def test_c01_01_round_trip_all_fixtures(self):
        for fixture in all_fixtures():
            with self.subTest(agent=fixture.agent_type, run=fixture.run_id):
                restored = type(fixture).model_validate_json(fixture.model_dump_json())
                self.assertEqual(restored, fixture)
                self.assertEqual(restored.as_of.tzinfo, timezone.utc)
                self.assertEqual(set(json.loads(fixture.model_dump_json())), set(type(fixture).model_fields))
        self.assertEqual(len(all_fixtures()), 12)
        with self.assertRaises(ValueError):
            result_fixture("technical", "unknown")

    def test_c01_02_numeric_bounds_and_strict_input(self):
        parameter = result_fixture("technical").parameters[0].model_dump()
        for value in (-0.1, 10.1, float("nan"), float("inf"), float("-inf"), True, False, "0", "10"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                ParameterScore.model_validate({**parameter, "score": value})
        for value in (0, 10, 0.0, 10.0, Decimal("6.5")):
            self.assertEqual(ParameterScore.model_validate({**parameter, "score": value}).score, float(value))
        for field in ("weight", "score"):
            for value in (float("nan"), float("inf"), True, "1", -1):
                with self.subTest(field=field, value=value), self.assertRaises(ValidationError):
                    ParameterScore.model_validate({**parameter, field: value})
        for field in ("coverage", "final_score"):
            for value in (float("nan"), float("inf"), True, "1", -1, 101):
                with self.subTest(field=field, value=value), self.assertRaises(ValidationError):
                    AgentResult.model_validate({**result_fixture("technical").model_dump(), field: value})

    def test_c01_03_invalid_variants_duplicates_metadata_extras(self):
        result = result_fixture("technical").model_dump()
        invalid = [
            {**result, "details": result_fixture("fundamental").details.model_dump()},
            {**result, "parameters": (*result["parameters"], result["parameters"][0])},
            {**result, "unexpected": "value"},
            {key: value for key, value in result.items() if key != "company"},
            {**result, "as_of": "2026-01-01T12:00:00"},
            {**result, "status": "failed"},
            {**result, "status": "insufficient_data"},
            {**result, "final_score": None},
            {**result, "evidence": (*result["evidence"], result["evidence"][0])},
            {**result, "evidence": [{**result["evidence"][0], "run_id": "foreign-run"}]},
            {**result, "schema_version": "99"},
        ]
        for index, payload in enumerate(invalid):
            with self.subTest(index=index), self.assertRaises(ValidationError):
                AgentResult.model_validate(payload)
        for key in ("source", "provenance", "excerpt", "observation"):
            payload = result["evidence"][0].copy()
            payload.pop(key)
            with self.subTest(missing=key), self.assertRaises(ValidationError):
                EvidenceReference.model_validate(payload)
        with self.assertRaises(ValidationError):
            EvidenceReference.model_validate({**result["evidence"][0], "excerpt": None, "observation": None})
        with self.assertRaises(ValidationError):
            EvidenceReference.model_validate({**result["evidence"][0], "excerpt": "x" * 4001})
        # An observation without an excerpt is a valid evidence form.
        EvidenceReference.model_validate({**result["evidence"][0], "excerpt": None})
        normalized = AgentResult.model_validate({**result, "as_of": "2026-07-01T17:30:00+05:30"})
        self.assertEqual(normalized.as_of.hour, 12)

    def test_c01_04_model_has_no_authority_to_override_server_fields(self):
        for agent, schema in MODEL_OUTPUT_SCHEMAS.items():
            payload = self.model_payload(agent)
            output = schema.model_validate(payload)
            self.assertEqual(schema.model_validate_json(output.model_dump_json()), output)
            schema.model_json_schema()  # Actual structured-output providers need a JSON schema.
            for field, value in {
                "company": {"id": "foreign"}, "agent_type": "news", "as_of": "2026-01-01",
                "assessment_date": "2026-01-01", "coverage": 100, "final_score": 10,
                "run_id": "foreign", "weight": 1, "evidence_dates": [],
            }.items():
                with self.subTest(agent=agent, field=field), self.assertRaises(ValidationError):
                    schema.model_validate({**payload, field: value})
            with self.assertRaises(ValidationError):
                schema.model_validate({**payload, "parameters": [{**payload["parameters"][0], "weight": 999}]})
            with self.assertRaises(ValidationError):
                schema.model_validate({**payload, "parameters": payload["parameters"] * 2})
        news = self.model_payload(AgentType.NEWS)
        for field, value in (("weight", 6), ("event_date", "2026-07-01"), ("eligible", True)):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                NewsModelOutput.model_validate({**news, "events": [{**news["events"][0], field: value}]})
        result = result_fixture("technical")
        context = self.context(result)
        with self.assertRaises(ValidationError):
            context.company = CompanySnapshot(id="other", name="Other", ticker="OTHER.NS")
        with self.assertRaises(ValidationError):
            context.company.id = "other"

    def test_c01_05_unknown_citations_and_foreign_publication(self):
        for agent in AgentType:
            result = result_fixture(agent)
            payload = result.model_dump()
            payload["parameters"][0]["evidence_ids"] = ["unknown"]
            with self.subTest(agent=agent), self.assertRaises(ValidationError):
                AgentResult.model_validate(payload)
            context = self.context(result)
            self.assertEqual(validate_result(result, context, known_evidence_ids={"evidence-1"},
                                             known_artifact_ids={"chart-1", "data-1"}), result)
            with self.assertRaises(AnalysisError) as raised:
                validate_result(result, context, known_evidence_ids=set(), known_artifact_ids={"chart-1", "data-1"})
            self.assertEqual(raised.exception.code, ErrorCode.INVALID_OUTPUT)
        result = result_fixture("technical")
        for field, value in (("run_id", "other"), ("agent_type", AgentType.NEWS),
                             ("company", CompanySnapshot(id="other", name="Other", ticker="OTHER.NS")),
                             ("as_of", datetime(2025, 1, 1, tzinfo=timezone.utc))):
            context = self.context(result).model_copy(update={field: value})
            with self.subTest(field=field), self.assertRaises(AnalysisError):
                validate_result(result, context, known_evidence_ids={"evidence-1"}, known_artifact_ids={"chart-1", "data-1"})
        with self.assertRaises(AnalysisError):
            validate_result(result, self.context(result), known_evidence_ids={"evidence-1"}, known_artifact_ids=set())
        payload = result.model_dump()
        payload["details"]["observations"][0]["evidence_ids"] = ["foreign"]
        with self.assertRaises(ValidationError):
            AgentResult.model_validate(payload)
        payload = result_fixture("fundamental").model_dump()
        payload["details"]["sector_evidence_ids"] = ["foreign"]
        with self.assertRaises(ValidationError):
            AgentResult.model_validate(payload)
        # Revalidate copies so bypassing Pydantic through model_copy cannot publish a malformed result.
        with self.assertRaises(ValidationError):
            validate_result(result.model_copy(update={"final_score": float("nan")}), self.context(result),
                            known_evidence_ids={"evidence-1"}, known_artifact_ids=set())

    def test_c01_06_registry_is_explicit_and_injectable(self):
        local = AgentRegistry()
        self.assertEqual(local.available(), ())
        for invalid in ("unknown", None, []):
            with self.subTest(invalid=invalid), self.assertRaises(AnalysisError) as raised:
                local.resolve(invalid)
            self.assertEqual(raised.exception.code, ErrorCode.INVALID_AGENT)
        for agent in AgentType:
            with self.assertRaises(AnalysisError) as raised:
                local.resolve(agent)
            self.assertEqual(raised.exception.code, ErrorCode.AGENT_UNAVAILABLE)
        class InjectedAdapter:
            def run(self, context):
                return result_fixture(context.agent_type, run_id=context.run_id,
                                      company=context.company, as_of=context.as_of)
        adapter = InjectedAdapter()
        local.register("technical", adapter)
        self.assertIs(local.resolve("technical"), adapter)
        result = result_fixture("technical")
        self.assertEqual(local.resolve("technical").run(self.context(result)), result)
        self.assertEqual(local.available(), (AgentType.TECHNICAL,))
        with self.assertRaises(ValueError):
            local.register("technical", adapter)
        with self.assertRaises(TypeError):
            local.register("fundamental", object())
        self.assertEqual(registry.available(), ())

    def test_safe_failure_catalog_rejects_raw_errors(self):
        for code in ErrorCode:
            error = AnalysisError(code)
            self.assertEqual(error.as_safe_error().message, str(error))
            SafeError.model_validate_json(error.as_safe_error().model_dump_json())
        with self.assertRaises(ValidationError):
            SafeError(code=ErrorCode.PROVIDER_UNAVAILABLE, message="secret sentinel raw provider URL")
        for agent in AgentType:
            fixture = failed_run_fixture(agent)
            self.assertIsNone(FailedRunFixture.model_validate_json(fixture.model_dump_json()).result)


if __name__ == "__main__":
    unittest.main()
