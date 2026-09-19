"""C03 offline provider boundaries; no live requests or secret lookups."""
import io
import logging
import os
import time
import unittest
from unittest.mock import Mock, patch

import httpx
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from openai import AzureOpenAI, AuthenticationError, BadRequestError, RateLimitError, InternalServerError
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.analysis.contracts import AgentType, AnalysisError, ErrorCode, ModelConfiguration
from app.analysis.provider_budget import LocalCallBudget
from app.analysis.provider_config import AnalysisProviderSettings
from app.analysis.provider_runtime import invoke_structured_agent
from app.resources import AzureResourceClients, ResourceSettings
import test_resources


class ProbeOutput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    value: int = Field(strict=True, ge=0)


class ScriptedModel(BaseChatModel):
    responses: list
    calls: int = 0
    timeouts: list[float] = Field(default_factory=list)

    @property
    def _llm_type(self):
        return 'scripted-tools'

    def bind_tools(self, tools, **kwargs):
        return self.bind(**kwargs)

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.timeouts.append(kwargs.get('timeout'))
        item = self.responses[self.calls]
        self.calls += 1
        if isinstance(item, Exception):
            raise item
        if callable(item):
            item = item(messages)
        return ChatResult(generations=[ChatGeneration(message=item)])


def answer(value):
    return AIMessage(content='', tool_calls=[{'name': 'ProbeOutput', 'args': {'value': value}, 'id': 'structured', 'type': 'tool_call'}])


def provider_error(error_class, status):
    return error_class('sentinel-secret https://sentinel.private/key', response=httpx.Response(status, request=httpx.Request('POST', 'https://sentinel.private/key')), body={'error': 'sentinel-secret'})


class AnalysisProviderTests(unittest.TestCase):
    def settings(self, **overrides):
        baseline = test_resources.ResourceSettingsTests()
        baseline.setUp()
        with patch.dict(os.environ, baseline.environment | overrides, clear=True):
            return ResourceSettings.from_environment()

    def invoke(self, responses, **kwargs):
        model = ScriptedModel(responses=responses)
        budget = kwargs.pop('budget', LocalCallBudget(time.monotonic() + 300))
        result = invoke_structured_agent(model=model, schema=ProbeOutput, messages=[HumanMessage(content='probe')], budget=budget, **kwargs)
        return result, model, budget

    def test_c03_01_defaults_and_agent_overrides(self):
        settings = self.settings(ANALYSIS_TECHNICAL_DEPLOYMENT='vision')
        clients = AzureResourceClients(settings, Mock())
        self.assertEqual(clients.analysis_model_configuration('technical').deployment, 'vision')
        for agent in ('fundamental', 'news'):
            self.assertEqual(clients.analysis_model_configuration(agent).deployment, 'terra')
        for agent in AgentType:
            settings = self.settings(**{f'ANALYSIS_{agent.value.upper()}_DEPLOYMENT': f'{agent}-override'})
            self.assertEqual(settings.analysis.model_configuration(agent, settings.openai).deployment, f'{agent}-override')
        with self.assertRaises(AnalysisError):
            AnalysisProviderSettings().model_configuration('unknown', settings.openai)

    def test_c03_02_optional_tavily_is_lazy_and_missing_is_safe(self):
        secrets = Mock()
        clients = AzureResourceClients(self.settings(), secrets)
        clients.analysis_model_configuration('fundamental')
        secrets.get.assert_not_called()
        with self.assertRaises(AnalysisError) as caught:
            clients.tavily_api_key()
        self.assertEqual(caught.exception.code, ErrorCode.CONFIGURATION_ERROR)
        secrets.get.assert_not_called()
        clients = AzureResourceClients(self.settings(TAVILY_API_KEY_SECRET='tavily'), secrets)
        secrets.get.return_value = 'secret'
        self.assertEqual(clients.tavily_api_key(), 'secret')
        secrets.get.side_effect = RuntimeError('sentinel-secret')
        with self.assertRaises(AnalysisError):
            clients.tavily_api_key()

    def test_c03_03_real_graph_runs_tool_then_validated_schema(self):
        observations = []
        def inspect_value() -> int:
            """Read the synthetic test value."""
            observations.append('executed')
            return 17
        tool_call = AIMessage(content='', tool_calls=[{'name':'inspect_value','args':{},'id':'read','type':'tool_call'}])
        result, model, budget = self.invoke([tool_call, answer(17)], tools=[inspect_value])
        self.assertEqual(result.value, 17)
        self.assertEqual(observations, ['executed'])
        self.assertEqual(budget.model_calls, 2)
        self.assertTrue(all(0 < value <= 45 for value in model.timeouts))

    def test_c03_04_repairs_are_bounded_and_counted(self):
        for responses, expected in [([answer('bad'), answer(1)], 2), ([answer('bad'), answer(-1), answer(1)], 3)]:
            result, model, budget = self.invoke(responses)
            self.assertEqual((result.value, model.calls, budget.model_calls), (1, expected, expected))
        model = ScriptedModel(responses=[answer('bad')] * 4)
        budget = LocalCallBudget(time.monotonic() + 300)
        with self.assertRaises(AnalysisError) as caught:
            invoke_structured_agent(model=model, schema=ProbeOutput, messages=[], budget=budget)
        self.assertEqual(caught.exception.code, ErrorCode.INVALID_OUTPUT)
        self.assertEqual((model.calls, budget.model_calls), (3, 3))

    def test_c03_05_retry_counts_and_auth_never_retried(self):
        sleeps = []
        result, model, budget = self.invoke([TimeoutError('private'), answer(1)], sleep=sleeps.append)
        self.assertEqual((model.calls, budget.model_calls, sleeps), (2, 2, [0.5]))
        result, model, budget = self.invoke([provider_error(RateLimitError, 429), answer(1)], sleep=lambda _: None)
        self.assertEqual(model.calls, 2)
        result, model, budget = self.invoke([provider_error(InternalServerError, 503), answer(1)], sleep=lambda _: None)
        self.assertEqual(model.calls, 2)
        for failures, calls, code in [([TimeoutError('private')] * 4, 3, ErrorCode.PROVIDER_UNAVAILABLE), ([provider_error(AuthenticationError, 401)] * 4, 1, ErrorCode.CONFIGURATION_ERROR)]:
            model = ScriptedModel(responses=failures)
            with self.assertRaises(AnalysisError) as caught:
                invoke_structured_agent(model=model, schema=ProbeOutput, messages=[], budget=LocalCallBudget(time.monotonic()+300), sleep=lambda _: None)
            self.assertEqual((model.calls, caught.exception.code), (calls, code))
        budget = LocalCallBudget(0.4, clock=lambda: 0)
        with self.assertRaises(AnalysisError) as caught:
            self.invoke([TimeoutError()], budget=budget, sleep=lambda _: self.fail('No time for backoff'))
        self.assertEqual(caught.exception.code, ErrorCode.DEADLINE_EXCEEDED)

    def test_c03_05_budget_deadline_and_output_are_checked(self):
        with self.assertRaises(ValueError):
            LocalCallBudget(float('nan'))
        with self.assertRaises(AnalysisError) as caught:
            self.invoke([answer('bad'), answer(1)], budget=LocalCallBudget(time.monotonic()+300, max_model_calls=1))
        self.assertEqual(caught.exception.code, ErrorCode.BUDGET_EXHAUSTED)
        with self.assertRaises(AnalysisError):
            LocalCallBudget(0, clock=lambda: 1).remaining_seconds()
        for image, code in [(True, ErrorCode.UNSUPPORTED_IMAGE_INPUT), (False, ErrorCode.CONFIGURATION_ERROR)]:
            with self.assertRaises(AnalysisError) as caught:
                self.invoke([provider_error(BadRequestError, 400)], image_input=image)
            self.assertEqual(caught.exception.code, code)

    def test_invalid_output_and_graph_configuration_are_safe(self):
        with self.assertRaises(ValidationError) as invalid:
            ProbeOutput(value='bad')
        with self.assertRaises(AnalysisError) as caught:
            self.invoke([invalid.exception])
        self.assertEqual(caught.exception.code, ErrorCode.INVALID_OUTPUT)
        with self.assertRaises(AnalysisError) as caught:
            self.invoke([AIMessage(content='No structured response')])
        self.assertEqual(caught.exception.code, ErrorCode.INVALID_OUTPUT)
        with self.assertRaises(AnalysisError) as caught:
            invoke_structured_agent(model=ScriptedModel(responses=[]), schema=object(), messages=[], budget=LocalCallBudget(time.monotonic()+300))
        self.assertEqual(caught.exception.code, ErrorCode.INVALID_OUTPUT)

    def test_expired_inflight_response_is_rejected(self):
        clock = [0]
        def finish_late(_messages):
            clock[0] = 11
            return answer(1)
        with self.assertRaises(AnalysisError) as caught:
            self.invoke([finish_late], budget=LocalCallBudget(10, clock=lambda: clock[0]))
        self.assertEqual(caught.exception.code, ErrorCode.DEADLINE_EXCEEDED)

    def test_tool_failures_use_safe_typed_errors(self):
        for failure in (RuntimeError('sentinel-secret'), AnalysisError(ErrorCode.BUDGET_EXHAUSTED)):
            def broken_tool() -> int:
                """Read a synthetic provider that fails."""
                raise failure
            call = AIMessage(content='', tool_calls=[{'name':'broken_tool','args':{},'id':'broken','type':'tool_call'}])
            with self.assertRaises(AnalysisError) as caught:
                self.invoke([call], tools=[broken_tool])
            expected = failure.code if isinstance(failure, AnalysisError) else ErrorCode.PROVIDER_UNAVAILABLE
            self.assertEqual(caught.exception.code, expected)
            self.assertNotIn('sentinel', str(caught.exception))

    def test_c03_06_provider_errors_are_redacted(self):
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        logging.getLogger().addHandler(handler)
        try:
            with self.assertRaises(AnalysisError) as caught:
                self.invoke([provider_error(AuthenticationError, 401)])
            serialized = caught.exception.as_safe_error().model_dump_json() + stream.getvalue()
            self.assertNotIn('sentinel', serialized)
            self.assertNotIn('https:', serialized)
        finally:
            logging.getLogger().removeHandler(handler)

    def test_c03_07_embedding_sdk_construction_and_shape(self):
        def handle(request):
            self.assertIn('/embeddings', request.url.path)
            return httpx.Response(200, json={'object':'list','model':'embedding-small','data':[{'object':'embedding','index':0,'embedding':[0.1,0.2,0.3]}],'usage':{'prompt_tokens':1,'total_tokens':1}})
        with httpx.Client(transport=httpx.MockTransport(handle)) as transport:
            client = AzureOpenAI(api_key='test', api_version='2025-04-01-preview', azure_endpoint='https://example.openai.azure.com', http_client=transport)
            result = client.with_options(timeout=20, max_retries=1).embeddings.create(model='embedding-small', input=['synthetic'])
            self.assertEqual(result.data[0].embedding, [0.1, 0.2, 0.3])

    def test_c03_07_chat_model_is_lazy_and_sdk_retries_disabled(self):
        secrets = Mock()
        secrets.get.return_value = 'test'
        clients = AzureResourceClients(self.settings(), secrets)
        secrets.get.assert_not_called()
        model = clients.analysis_chat_model('technical')
        self.assertEqual(model.max_retries, 0)
        self.assertEqual(model.request_timeout, 45)
        self.assertEqual(model.deployment_name, 'terra')
        with self.assertRaises(AnalysisError):
            clients.analysis_chat_model('technical', timeout=46)
        secrets.get.side_effect = RuntimeError('sentinel-secret')
        with self.assertRaises(AnalysisError) as caught:
            clients.analysis_chat_model('technical')
        self.assertNotIn('sentinel', str(caught.exception))

    def test_queued_model_configuration_overrides_changed_environment(self):
        clients = AzureResourceClients(self.settings(ANALYSIS_TECHNICAL_DEPLOYMENT='new-deployment'), Mock())
        clients.secrets.get.return_value = 'test'
        frozen = ModelConfiguration(deployment='queued-deployment', api_version='2025-01-01-preview')
        model = clients.analysis_chat_model('technical', configuration=frozen)
        self.assertEqual(model.deployment_name, 'queued-deployment')
        self.assertEqual(model.openai_api_version, '2025-01-01-preview')
        self.assertEqual(clients.analysis_model_configuration('technical').deployment, 'new-deployment')


if __name__ == '__main__':
    unittest.main()
