"""API contract tests (RAG endpoint stubbed; extraction runs for real)."""

from fastapi.testclient import TestClient

import ledgerlens.api.routes as routes
from ledgerlens.api.main import create_app


def _client() -> TestClient:
    return TestClient(create_app())


def test_health():
    r = _client().get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_extract_endpoint_roundtrip(invoice_pdf):
    path, truth = invoice_pdf
    with open(path, "rb") as f:
        r = _client().post("/extract", files={"file": ("inv.pdf", f.read(), "application/pdf")})
    assert r.status_code == 200
    body = r.json()
    assert body["fields"]["invoice_no"]["value"] == truth["invoice_no"]
    assert isinstance(body["findings"], list)


def test_extract_rejects_non_pdf():
    r = _client().post("/extract", files={"file": ("x.txt", b"hi", "text/plain")})
    assert r.status_code == 422


def test_ask_stubbed(monkeypatch):
    monkeypatch.setattr(
        routes, "ask", lambda q, provider=None: {"answer": "ok", "provider": "fake", "sources": []}
    )
    r = _client().post("/ask", json={"question": "what are the rules?", "provider": "fake"})
    assert r.status_code == 200
    assert r.json()["answer"] == "ok"


def test_ledger_503_when_missing(monkeypatch, tmp_path):
    from ledgerlens.settings import get_config

    cfg = get_config()
    original = cfg["extraction"]["ledger_path"]
    cfg["extraction"]["ledger_path"] = str(tmp_path / "nope.parquet")
    try:
        assert _client().get("/ledger").status_code == 503
    finally:
        cfg["extraction"]["ledger_path"] = original
