"""Ollama provider over plain HTTP (no SDK dependency)."""

from __future__ import annotations

import json
from collections.abc import Iterator

import httpx

from ledgerlens.settings import get_settings


class OllamaProvider:
    name = "ollama"

    def __init__(self, model: str | None = None, base_url: str | None = None):
        settings = get_settings()
        self.model = model or settings.ollama_model
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")

    def _payload(self, prompt: str, system: str | None, max_tokens: int, stream: bool) -> dict:
        return {
            "model": self.model,
            "prompt": prompt,
            "system": system or "",
            "stream": stream,
            "options": {"num_predict": max_tokens},
        }

    def complete(self, prompt: str, *, system: str | None = None, max_tokens: int = 1024) -> str:
        r = httpx.post(
            f"{self.base_url}/api/generate",
            json=self._payload(prompt, system, max_tokens, stream=False),
            timeout=300,
        )
        r.raise_for_status()
        return r.json()["response"]

    def stream(
        self, prompt: str, *, system: str | None = None, max_tokens: int = 1024
    ) -> Iterator[str]:
        with httpx.stream(
            "POST",
            f"{self.base_url}/api/generate",
            json=self._payload(prompt, system, max_tokens, stream=True),
            timeout=300,
        ) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line:
                    continue
                data = json.loads(line)
                if chunk := data.get("response"):
                    yield chunk
                if data.get("done"):
                    break
