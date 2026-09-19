"""Explicit adapter registration; production has no simulated fallback."""

from .contracts import AgentAdapter, AgentType, AnalysisError, ErrorCode


class AgentRegistry:
    def __init__(self):
        self._adapters: dict[AgentType, AgentAdapter] = {}

    @staticmethod
    def _agent_type(agent_type: AgentType | str) -> AgentType:
        try:
            return AgentType(agent_type)
        except (ValueError, TypeError):
            raise AnalysisError(ErrorCode.INVALID_AGENT) from None

    def register(self, agent_type: AgentType | str, adapter: AgentAdapter) -> None:
        key = self._agent_type(agent_type)
        if key in self._adapters:
            raise ValueError("An adapter is already registered for this agent.")
        if not callable(getattr(adapter, "run", None)):
            raise TypeError("An adapter must expose run(context).")
        self._adapters[key] = adapter

    def resolve(self, agent_type: AgentType | str) -> AgentAdapter:
        key = self._agent_type(agent_type)
        if key not in self._adapters:
            raise AnalysisError(ErrorCode.AGENT_UNAVAILABLE)
        return self._adapters[key]

    def available(self) -> tuple[AgentType, ...]:
        return tuple(key for key in AgentType if key in self._adapters)


registry = AgentRegistry()
