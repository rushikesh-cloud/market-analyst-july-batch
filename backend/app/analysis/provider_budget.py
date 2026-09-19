"""Provider call budget protocol shared with durable worker implementations."""

from dataclasses import dataclass
import math
import time
from typing import Callable, Protocol

from .contracts import AnalysisError, ErrorCode


class CallBudget(Protocol):
    def remaining_seconds(self) -> float: ...

    def reserve_model_call(self) -> float:
        """Persist consumption before calling the provider; return allowed timeout."""
        ...


@dataclass
class LocalCallBudget:
    """In-memory budget for tests/smokes; durable execution supplies CallBudget."""

    deadline: float
    model_calls: int = 0
    max_model_calls: int = 10
    clock: Callable[[], float] = time.monotonic

    def __post_init__(self):
        if not math.isfinite(self.deadline) or not 0 <= self.model_calls <= self.max_model_calls <= 10:
            raise ValueError("Invalid execution budget.")

    def remaining_seconds(self) -> float:
        remaining = self.deadline - self.clock()
        if remaining <= 0:
            raise AnalysisError(ErrorCode.DEADLINE_EXCEEDED)
        return remaining

    def reserve_model_call(self) -> float:
        timeout = min(45.0, self.remaining_seconds())
        if self.model_calls >= self.max_model_calls:
            raise AnalysisError(ErrorCode.BUDGET_EXHAUSTED)
        self.model_calls += 1
        return timeout
