"""API routes: /audit and /extract (upload), /ledger, /findings, /ask, /metrics, /health."""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from ledgerlens.gateway.audit import audit_invoice
from ledgerlens.gateway.circuit import breaker_for
from ledgerlens.gateway.policy_qa import guarded_ask
from ledgerlens.llm.factory import get_provider
from ledgerlens.observability.metrics import REGISTRY
from ledgerlens.settings import get_config, get_settings, resolve_path

logger = logging.getLogger(__name__)
router = APIRouter()


class AskRequest(BaseModel):
    question: str = Field(min_length=5, max_length=1000)
    provider: str | None = None


@router.get("/health")
def health() -> dict[str, str]:
    provider = get_settings().llm_provider
    return {"status": "ok", "provider": provider, "llm_circuit": breaker_for(provider).state}


@router.get("/metrics", response_class=PlainTextResponse)
def metrics() -> str:
    return REGISTRY.render()


def _ledger() -> pd.DataFrame:
    path = resolve_path(get_config()["extraction"]["ledger_path"])
    if not path.exists():
        raise HTTPException(
            status_code=503,
            detail="Ledger missing. Run corpus generate + extraction pipeline first.",
        )
    return pd.read_parquet(path)


@router.get("/ledger")
def ledger(limit: int = 100) -> list[dict]:
    df = _ledger().head(limit)
    return json.loads(df.to_json(orient="records"))


@router.get("/findings")
def findings() -> list[dict]:
    df = _ledger()
    flagged = df[df["n_findings"] > 0]
    out = []
    for _, row in flagged.iterrows():
        out.append(
            {
                "file": row["file"],
                "invoice_no": row["invoice_no"],
                "vendor": row["vendor"],
                "total": row["total"],
                "findings": json.loads(row["findings"]),
            }
        )
    return out


async def _run_upload(file: UploadFile, *, ground: bool) -> dict:
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=422, detail="Only PDF files are accepted")
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(await file.read())
        tmp_path = Path(tmp.name)
    try:
        return audit_invoice(tmp_path, file.filename, ground=ground)
    finally:
        tmp_path.unlink(missing_ok=True)


@router.post("/extract")
async def extract(file: UploadFile) -> dict:
    """Fields + findings only; no policy lookup."""
    return await _run_upload(file, ground=False)


@router.post("/audit")
async def audit(file: UploadFile) -> dict:
    """Fields, findings with the governing policy clause, review fields, stage timings."""
    return await _run_upload(file, ground=True)


@router.post("/ask")
def ask_endpoint(request: AskRequest) -> dict:
    try:
        provider = get_provider(request.provider)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        return guarded_ask(request.question, provider=provider)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
