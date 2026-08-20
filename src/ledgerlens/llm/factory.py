"""The swap point: build the configured LLM provider from settings."""

from __future__ import annotations

from ledgerlens.llm.base import FakeProvider, LLMProvider
from ledgerlens.settings import get_settings


def get_provider(name: str | None = None) -> LLMProvider:
    """Return the provider named by `name` or the LLM_PROVIDER env var."""
    provider = (name or get_settings().llm_provider).lower()
    if provider == "claude":
        from ledgerlens.llm.claude import ClaudeProvider

        return ClaudeProvider()
    if provider == "ollama":
        from ledgerlens.llm.ollama import OllamaProvider

        return OllamaProvider()
    if provider == "fake":
        return FakeProvider()
    raise ValueError(f"Unknown LLM provider: {provider!r} (expected claude|ollama|fake)")
