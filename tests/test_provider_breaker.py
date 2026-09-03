"""Provider breaker state machine (fake clock) and the degraded /ask path."""

import pytest

from ledgerlens.gateway.circuit import ProviderBreaker
from ledgerlens.gateway.policy_qa import guarded_ask
from ledgerlens.llm.base import FakeProvider
from ledgerlens.observability.metrics import REGISTRY


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class _DownProvider(FakeProvider):
    name = "down"

    def complete(self, prompt, *, system=None, max_tokens=1024):
        self.calls.append({"prompt": prompt})
        raise ConnectionError("connection refused")


def _breaker(threshold=3, cooldown=30.0):
    clock = _Clock()
    return ProviderBreaker(failure_threshold=threshold, cooldown_s=cooldown, clock=clock), clock


def test_opens_only_after_consecutive_failures():
    b, _ = _breaker(threshold=3)
    b.record_failure()
    b.record_failure()
    b.record_success()  # a success in between resets the streak
    b.record_failure()
    b.record_failure()
    assert b.state == "closed" and b.allow()
    b.record_failure()
    assert b.state == "open" and not b.allow()


def test_half_open_admits_exactly_one_probe_until_it_reports():
    b, clock = _breaker(threshold=1, cooldown=30.0)
    b.record_failure()
    assert not b.allow()
    clock.now += 29.9
    assert not b.allow() and b.retry_after_s() == pytest.approx(0.1)
    clock.now += 0.2
    assert b.state == "half_open"
    assert b.allow()  # the probe
    assert not b.allow()  # nobody else while the probe is in flight
    b.record_success()
    assert b.state == "closed" and b.allow()


def test_failed_probe_reopens_with_a_fresh_cooldown():
    b, clock = _breaker(threshold=1, cooldown=30.0)
    b.record_failure()
    clock.now += 31
    assert b.allow()
    b.record_failure()
    assert b.state == "open" and b.retry_after_s() == pytest.approx(30.0)


def test_ask_degrades_instead_of_raising_and_stops_calling_after_threshold(policy_kb):
    REGISTRY.reset()
    provider = _DownProvider()
    b, _ = _breaker(threshold=2)
    replies = [guarded_ask("Can we accept 90-day payment terms?", provider, b) for _ in range(4)]
    assert all(r["answer"] is None and r["degraded"] for r in replies)
    assert all(r["sources"] for r in replies), "retrieved excerpts still come back"
    assert [r["circuit"] for r in replies] == ["closed", "open", "open", "open"]
    assert len(provider.calls) == 2, "the open circuit must not hit the provider"
    assert REGISTRY.value("ledgerlens_ask_total", outcome="degraded") == 2
    assert REGISTRY.value("ledgerlens_ask_total", outcome="rejected") == 2


def test_ask_answers_when_provider_is_healthy(policy_kb):
    provider = FakeProvider(canned="Terms over 60 days need CFO approval [expense-policy].")
    b, _ = _breaker()
    reply = guarded_ask("Can we accept 90-day payment terms?", provider, b)
    assert reply["degraded"] is False and "CFO" in reply["answer"]
    assert "Policy excerpts" in provider.calls[0]["prompt"]
    assert reply["sources"][0]["section"]
