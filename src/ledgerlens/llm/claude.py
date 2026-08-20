"""Claude API provider (Anthropic SDK)."""

from __future__ import annotations

from collections.abc import Iterator

from ledgerlens.settings import get_settings


class ClaudeProvider:
    name = "claude"

    def __init__(self, model: str | None = None, api_key: str | None = None):
        import anthropic

        settings = get_settings()
        self.model = model or settings.anthropic_model
        self.client = anthropic.Anthropic(api_key=api_key or settings.anthropic_api_key or None)

    def complete(self, prompt: str, *, system: str | None = None, max_tokens: int = 1024) -> str:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system or "",
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(block.text for block in response.content if block.type == "text")

    def stream(
        self, prompt: str, *, system: str | None = None, max_tokens: int = 1024
    ) -> Iterator[str]:
        with self.client.messages.stream(
            model=self.model,
            max_tokens=max_tokens,
            system=system or "",
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            yield from stream.text_stream
