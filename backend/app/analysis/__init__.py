"""Shared analysis foundation. Agent business logic lives in dedicated subpackages."""

from .contracts import AgentResult, AgentType, AnalysisContext
from .registry import AgentRegistry

__all__ = ["AgentRegistry", "AgentResult", "AgentType", "AnalysisContext"]
