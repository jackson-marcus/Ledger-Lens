"""The LLM provider contract.

A deliberately thin abstraction (instead of LangChain): two methods, plain
strings in and out. Providers are hot-swappable via the LLM_PROVIDER env var
without touching any calling code.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    """Anything that can complete a prompt, optionally streaming."""

    name: str

    def complete(self, prompt: str, *, system: str | None = None, max_tokens: int = 1024) -> str:
        """Return the full completion as a string."""
        ...

    def stream(
        self, prompt: str, *, system: str | None = None, max_tokens: int = 1024
    ) -> Iterator[str]:
        """Yield completion text chunks as they arrive."""
        ...


class FakeProvider:
    """Deterministic provider for tests and offline development.

    Supports a scripted-response queue: each call pops the next response, so
    tests can simulate "bad SQL first, corrected SQL second" and exercise the
    agent's self-correction loop. With no script, echoes the first prompt line.
    """

    name = "fake"

    def __init__(self, canned: str | None = None, script: list[str] | None = None):
        self.canned = canned
        self.script = list(script) if script else []
        self.calls: list[dict] = []

    def complete(self, prompt: str, *, system: str | None = None, max_tokens: int = 1024) -> str:
        self.calls.append({"prompt": prompt, "system": system, "max_tokens": max_tokens})
        if self.script:
            return self.script.pop(0)
        if self.canned is not None:
            return self.canned
        first_line = prompt.strip().splitlines()[0] if prompt.strip() else ""
        return f"[fake-answer] {first_line[:120]}"

    def stream(
        self, prompt: str, *, system: str | None = None, max_tokens: int = 1024
    ) -> Iterator[str]:
        text = self.complete(prompt, system=system, max_tokens=max_tokens)
        for i in range(0, len(text), 16):
            yield text[i : i + 16]
