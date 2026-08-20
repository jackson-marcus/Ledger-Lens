"""API routes: /extract (upload), /ledger, /findings, /ask, /health."""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel, Field

from ledgerlens.extraction.extract import extract_pdf
from ledgerlens.llm.factory import get_provider
from ledgerlens.rag.qa import ask
from ledgerlens.settings import get_config, get_settings, resolve_path
from ledgerlens.validation.rules import validate_invoice

logger = logging.getLogger(__name__)
router = APIRouter()


class AskRequest(BaseModel):
    question: str = Field(min_length=5, max_length=1000)
    provider: str | None = None


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "provider": get_settings().llm_provider}


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


@router.post("/extract")
async def extract(file: UploadFile) -> dict:
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=422, detail="Only PDF files are accepted")
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(await file.read())
        tmp_path = Path(tmp.name)
    try:
        inv = extract_pdf(tmp_path)
        inv.file = file.filename
        result = inv.as_dict()
        result["findings"] = [f.as_dict() for f in validate_invoice(inv)]
        return result
    finally:
        tmp_path.unlink(missing_ok=True)


@router.post("/ask")
def ask_endpoint(request: AskRequest) -> dict:
    try:
        provider = get_provider(request.provider)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        return ask(request.question, provider=provider)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
