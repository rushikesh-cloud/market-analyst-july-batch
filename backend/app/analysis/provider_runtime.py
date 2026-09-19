"""Bounded LangChain structured agents with one explicit provider retry layer."""

import time
from typing import Callable, TypeVar

from langchain.agents import create_agent
from langchain.agents.middleware import wrap_model_call, wrap_tool_call
from langchain.agents.structured_output import ToolStrategy
from openai import APIConnectionError, APIStatusError, APITimeoutError
from pydantic import BaseModel, ValidationError

from .contracts import AnalysisError, ErrorCode
from .provider_budget import CallBudget

Output = TypeVar("Output", bound=BaseModel)


def _transient(error: Exception) -> bool:
    return isinstance(error, (TimeoutError, APITimeoutError, APIConnectionError)) or (
        isinstance(error, APIStatusError)
        and (error.status_code == 429 or error.status_code >= 500)
    )


def _failure_code(error: Exception, image_input: bool) -> ErrorCode:
    if isinstance(error, APIStatusError):
        if error.status_code in (401, 403, 404):
            return ErrorCode.CONFIGURATION_ERROR
        if error.status_code in (400, 422):
            return ErrorCode.UNSUPPORTED_IMAGE_INPUT if image_input else ErrorCode.CONFIGURATION_ERROR
    if isinstance(error, ValidationError):
        return ErrorCode.INVALID_OUTPUT
    return ErrorCode.PROVIDER_UNAVAILABLE


def invoke_structured_agent(
    *,
    model,
    schema: type[Output],
    messages: list,
    budget: CallBudget,
    tools: list | None = None,
    system_prompt: str | None = None,
    image_input: bool = False,
    sleep: Callable[[float], None] = time.sleep,
) -> Output:
    """Execute an actual create_agent graph; state and repair counts are invocation-local.

    Domain tools must reserve their own smaller caps before any external work.
    The worker supervises this synchronous function in its isolated child process.
    Neither exception strings nor raw tool/model prompts are logged here.
    """
    repairs = 0

    def repair(_error):
        nonlocal repairs
        if repairs >= 2:
            raise AnalysisError(ErrorCode.INVALID_OUTPUT)
        repairs += 1
        return "Return one structured response matching the required schema and field types."

    @wrap_model_call
    def provider_boundary(request, handler):
        for attempt in range(3):
            timeout = budget.reserve_model_call()
            try:
                response = handler(request.override(
                    model_settings={**request.model_settings, "timeout": timeout}
                ))
                budget.remaining_seconds()
                return response
            except AnalysisError:
                raise
            except Exception as error:
                if _transient(error) and attempt < 2:
                    delay = 0.5 * (2 ** attempt)
                    if budget.remaining_seconds() <= delay:
                        raise AnalysisError(ErrorCode.DEADLINE_EXCEEDED) from None
                    sleep(delay)
                    continue
                raise AnalysisError(_failure_code(error, image_input)) from None

    @wrap_tool_call
    def tool_boundary(request, handler):
        budget.remaining_seconds()
        try:
            response = handler(request)
        except AnalysisError:
            raise
        except Exception:
            raise AnalysisError(ErrorCode.PROVIDER_UNAVAILABLE) from None
        budget.remaining_seconds()
        return response

    try:
        graph = create_agent(
            model=model,
            tools=tools or [],
            system_prompt=system_prompt,
            response_format=ToolStrategy(schema, handle_errors=repair),
            middleware=[provider_boundary, tool_boundary],
        )
        state = graph.invoke({"messages": messages}, config={"recursion_limit": 100})
        budget.remaining_seconds()
        output = state.get("structured_response")
        if not isinstance(output, schema):
            raise AnalysisError(ErrorCode.INVALID_OUTPUT)
        return output
    except AnalysisError:
        raise
    except Exception:
        raise AnalysisError(ErrorCode.INVALID_OUTPUT) from None
