"""Per-stage timing for one invoice audit.

An audit is a short fixed sequence (parse PDF, validate, ground findings in
policy) and the interesting operational question is which of those is slow or
failing. Each stage is recorded with wall-clock milliseconds, a status, and a
small detail dict the stage fills in (finding counts, chunks retrieved), and
the same numbers are accumulated into the metrics registry.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any

from ledgerlens.observability.metrics import REGISTRY, MetricsRegistry


@dataclass
class StageSpan:
    name: str
    ms: float = 0.0
    status: str = "running"
    detail: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"stage": self.name, "ms": round(self.ms, 2), "status": self.status, **self.detail}


class StageTrace:
    def __init__(self, metrics: MetricsRegistry = REGISTRY) -> None:
        self.metrics = metrics
        self.spans: list[StageSpan] = []

    @contextmanager
    def stage(self, name: str) -> Iterator[StageSpan]:
        span = StageSpan(name=name)
        self.spans.append(span)
        started = perf_counter()
        try:
            yield span
        except Exception:
            span.status = "error"
            raise
        else:
            span.status = "ok"
        finally:
            span.ms = (perf_counter() - started) * 1000.0
            self.metrics.inc("ledgerlens_stage_runs_total", stage=name, status=span.status)
            self.metrics.inc("ledgerlens_stage_seconds_total", span.ms / 1000.0, stage=name)

    def total_ms(self) -> float:
        return sum(s.ms for s in self.spans)

    def as_list(self) -> list[dict[str, Any]]:
        return [s.as_dict() for s in self.spans]
