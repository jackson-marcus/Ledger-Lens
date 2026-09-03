"""Process-local counters for the audit service, rendered as Prometheus text.

What gets counted is deliberately domain-shaped rather than generic HTTP
plumbing: which validation rules fire, which extracted fields keep landing in
the human-review bucket, how often a finding could be tied to a policy clause,
and whether policy questions were answered by the LLM or served degraded.
"""

from __future__ import annotations

from collections import defaultdict
from threading import Lock

Labels = tuple[tuple[str, str], ...]


class MetricsRegistry:
    def __init__(self) -> None:
        self._lock = Lock()
        self._help: dict[str, str] = {}
        self._samples: dict[str, dict[Labels, float]] = defaultdict(dict)

    def describe(self, name: str, help_text: str) -> None:
        self._help[name] = help_text

    @staticmethod
    def _key(labels: dict[str, str]) -> Labels:
        return tuple(sorted((k, str(v)) for k, v in labels.items()))

    def inc(self, name: str, amount: float = 1.0, **labels: str) -> None:
        key = self._key(labels)
        with self._lock:
            series = self._samples[name]
            series[key] = series.get(key, 0.0) + amount

    def value(self, name: str, **labels: str) -> float:
        return self._samples.get(name, {}).get(self._key(labels), 0.0)

    def series(self, name: str) -> dict[Labels, float]:
        return dict(self._samples.get(name, {}))

    def reset(self) -> None:
        with self._lock:
            self._samples.clear()

    def render(self) -> str:
        lines: list[str] = []
        for name in sorted(set(self._help) | set(self._samples)):
            if name in self._help:
                lines.append(f"# HELP {name} {self._help[name]}")
            lines.append(f"# TYPE {name} counter")
            for labels, value in sorted(self._samples.get(name, {}).items()):
                label_str = ",".join(f'{k}="{v}"' for k, v in labels)
                sample = f"{name}{{{label_str}}}" if label_str else name
                text = (
                    f"{value:.6f}".rstrip("0").rstrip(".")
                    if value != int(value)
                    else str(int(value))
                )
                lines.append(f"{sample} {text}")
        return "\n".join(lines) + "\n"


REGISTRY = MetricsRegistry()
REGISTRY.describe("ledgerlens_findings_total", "Validation findings emitted, by rule and severity.")
REGISTRY.describe(
    "ledgerlens_review_fields_total",
    "Extracted fields whose confidence fell below extraction.min_confidence_flag.",
)
REGISTRY.describe(
    "ledgerlens_grounding_total",
    "Policy grounding outcomes per finding: cited, gated (retrieval disagreed), or skipped.",
)
REGISTRY.describe(
    "ledgerlens_ask_total",
    "Policy questions by outcome: answered, degraded (provider failed), rejected (circuit open).",
)
REGISTRY.describe("ledgerlens_stage_runs_total", "Audit stage executions, by stage and status.")
REGISTRY.describe("ledgerlens_stage_seconds_total", "Wall-clock seconds spent per audit stage.")
