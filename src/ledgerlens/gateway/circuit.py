"""Circuit breaker in front of the policy-QA LLM provider.

The policy assistant talks to a local Ollama daemon by default, and on a
developer box that daemon is frequently not running. Without a breaker every
/ask call pays the full connect/read timeout and then fails; with one, the
first few failures open the circuit and subsequent questions are answered
straight from retrieved policy excerpts until a cooldown elapses and a single
probe call is allowed through.

The clock is injectable so the state machine can be tested without sleeping.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class ProviderBreaker:
    failure_threshold: int = 3
    cooldown_s: float = 30.0
    clock: Callable[[], float] = field(default=time.monotonic, repr=False)
    consecutive_failures: int = 0
    opened_at: float | None = None
    probing: bool = False

    @property
    def state(self) -> str:
        if self.opened_at is None:
            return "closed"
        if self.probing:
            return "half_open"
        if self.clock() - self.opened_at >= self.cooldown_s:
            return "half_open"
        return "open"

    def allow(self) -> bool:
        """Whether a provider call may be attempted right now.

        Closed: always. Open: never. Half-open: exactly one probe until it
        reports back; further callers are rejected while the probe is in flight.
        """
        if self.opened_at is None:
            return True
        if self.probing:
            return False
        if self.clock() - self.opened_at >= self.cooldown_s:
            self.probing = True
            return True
        return False

    def record_success(self) -> None:
        self.consecutive_failures = 0
        self.opened_at = None
        self.probing = False

    def record_failure(self) -> None:
        self.consecutive_failures += 1
        if self.probing or self.consecutive_failures >= self.failure_threshold:
            self.opened_at = self.clock()
            self.probing = False

    def retry_after_s(self) -> float:
        if self.opened_at is None:
            return 0.0
        return max(0.0, self.cooldown_s - (self.clock() - self.opened_at))


_BREAKERS: dict[str, ProviderBreaker] = {}


def breaker_for(provider_name: str) -> ProviderBreaker:
    """One breaker per provider: Ollama being down must not block Claude."""
    if provider_name not in _BREAKERS:
        _BREAKERS[provider_name] = ProviderBreaker()
    return _BREAKERS[provider_name]


def reset_breakers() -> None:
    _BREAKERS.clear()
