"""API contract tests: extraction and audit run for real, the LLM is faked."""

from fastapi.testclient import TestClient

from ledgerlens.api.main import create_app
from ledgerlens.gateway.circuit import reset_breakers
from ledgerlens.observability.metrics import REGISTRY


def _client() -> TestClient:
    return TestClient(create_app())


def _upload(route: str, path):
    with open(path, "rb") as f:
        return _client().post(route, files={"file": ("inv.pdf", f.read(), "application/pdf")})


def test_health():
    reset_breakers()
    r = _client().get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["llm_circuit"] == "closed"


def test_extract_endpoint_roundtrip(invoice_pdf):
    path, truth = invoice_pdf
    r = _upload("/extract", path)
    assert r.status_code == 200
    body = r.json()
    assert body["fields"]["invoice_no"]["value"] == truth["invoice_no"]
    assert body["findings"] == []
    assert [s["stage"] for s in body["stages"]] == ["extract", "validate"]


def test_audit_grounds_bad_total_in_vendor_dispute_policy(make_pdf, policy_kb):
    path, _ = make_pdf(31, error="bad_total")
    r = _upload("/audit", path)
    assert r.status_code == 200
    body = r.json()
    by_rule = {f["rule"]: f for f in body["findings"]}
    assert body["max_severity"] == "error"
    assert by_rule["subtotal_plus_tax"]["policy"]["doc"] == "vendor-policy"
    assert by_rule["subtotal_plus_tax"]["policy"]["section"] == "Dispute process"
    assert [s["stage"] for s in body["stages"]] == ["extract", "validate", "ground"]
    assert body["stages"][2]["cited"] == 1


def test_metrics_reflect_what_the_audit_found(make_pdf, policy_kb):
    REGISTRY.reset()
    path, _ = make_pdf(32, error="crazy_tax")
    assert _upload("/audit", path).status_code == 200
    text = _client().get("/metrics").text
    assert 'ledgerlens_findings_total{rule="tax_rate_implausible",severity="error"} 1' in text
    assert 'ledgerlens_grounding_total{outcome="cited"} 1' in text
    assert 'ledgerlens_stage_runs_total{stage="ground",status="ok"} 1' in text
    assert "# TYPE ledgerlens_stage_seconds_total counter" in text


def test_extract_rejects_non_pdf():
    r = _client().post("/extract", files={"file": ("x.txt", b"hi", "text/plain")})
    assert r.status_code == 422


def test_ask_with_fake_provider_returns_cited_sources(policy_kb):
    r = _client().post(
        "/ask", json={"question": "What tax rate applies in Germany?", "provider": "fake"}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["degraded"] is False
    assert body["answer"].startswith("[fake-answer]")
    assert any(s["doc"] == "tax-policy" for s in body["sources"])


def test_ask_unknown_provider_is_422():
    r = _client().post("/ask", json={"question": "what are the rules?", "provider": "gpt"})
    assert r.status_code == 422


def test_ledger_503_when_missing(tmp_path):
    from ledgerlens.settings import get_config

    cfg = get_config()
    original = cfg["extraction"]["ledger_path"]
    cfg["extraction"]["ledger_path"] = str(tmp_path / "nope.parquet")
    try:
        assert _client().get("/ledger").status_code == 503
    finally:
        cfg["extraction"]["ledger_path"] = original
