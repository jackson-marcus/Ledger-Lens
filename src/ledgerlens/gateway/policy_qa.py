"""Policy questions answered through the provider breaker.

Retrieval always runs (it is local and cheap). The LLM call runs only when the
provider's breaker allows it; when the provider is down or the circuit is open
the caller still receives the retrieved excerpts, flagged as degraded, instead
of a stack trace after a long timeout.
"""

from __future__ import annotations

import logging

from ledgerlens.gateway.circuit import ProviderBreaker, breaker_for
from ledgerlens.llm.base import LLMProvider
from ledgerlens.observability.metrics import REGISTRY
from ledgerlens.rag import qa
from ledgerlens.settings import get_config

logger = logging.getLogger(__name__)


def guarded_ask(
    question: str, provider: LLMProvider, breaker: ProviderBreaker | None = None
) -> dict:
    breaker = breaker or breaker_for(provider.name)
    hits = qa.retrieve(question)
    base = {"provider": provider.name, "sources": qa.sources(hits)}

    if not breaker.allow():
        REGISTRY.inc("ledgerlens_ask_total", outcome="rejected")
        return {
            **base,
            "answer": None,
            "degraded": True,
            "reason": f"{provider.name} circuit open; retry in {breaker.retry_after_s():.0f}s",
            "circuit": breaker.state,
        }

    try:
        answer = provider.complete(
            qa.build_prompt(question, hits),
            system=qa.SYSTEM,
            max_tokens=get_config()["rag"]["max_answer_tokens"],
        )
    except Exception as exc:
        breaker.record_failure()
        REGISTRY.inc("ledgerlens_ask_total", outcome="degraded")
        logger.warning("policy provider %s failed (%s): %s", provider.name, breaker.state, exc)
        return {
            **base,
            "answer": None,
            "degraded": True,
            "reason": f"{provider.name} unavailable: {type(exc).__name__}",
            "circuit": breaker.state,
        }

    breaker.record_success()
    REGISTRY.inc("ledgerlens_ask_total", outcome="answered")
    return {**base, "answer": answer, "degraded": False, "circuit": breaker.state}
