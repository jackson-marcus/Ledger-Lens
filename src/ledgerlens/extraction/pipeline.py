"""Batch pipeline: extract + validate every invoice PDF into the ledger.

Usage:
    python -m ledgerlens.extraction.pipeline
"""

from __future__ import annotations

import json
import logging

import pandas as pd

from ledgerlens.extraction.extract import extract_pdf
from ledgerlens.settings import get_config, resolve_path
from ledgerlens.validation.rules import validate_invoice

logger = logging.getLogger(__name__)


def process_corpus() -> pd.DataFrame:
    cfg = get_config()
    pdf_dir = resolve_path(cfg["corpus"]["pdf_dir"])
    pdfs = sorted(pdf_dir.glob("*.pdf"))
    if not pdfs:
        raise FileNotFoundError(f"No PDFs in {pdf_dir}; run `python -m ledgerlens.corpus.generate`")

    rows = []
    seen: dict[str, str] = {}
    for pdf in pdfs:
        inv = extract_pdf(pdf)
        findings = validate_invoice(inv, seen)
        low_confidence = [
            name
            for name, fv in inv.fields.items()
            if fv.confidence < cfg["extraction"]["min_confidence_flag"]
        ]
        rows.append(
            {
                "file": pdf.name,
                "invoice_no": inv.get("invoice_no"),
                "vendor": inv.get("vendor"),
                "invoice_date": inv.get("invoice_date"),
                "due_date": inv.get("due_date"),
                "subtotal": inv.get("subtotal"),
                "tax": inv.get("tax"),
                "total": inv.get("total"),
                "n_lines": inv.get("n_lines"),
                "n_findings": len(findings),
                "max_severity": max((f.severity for f in findings), default=""),
                "findings": json.dumps([f.as_dict() for f in findings]),
                "review_fields": ",".join(low_confidence),
            }
        )
    df = pd.DataFrame(rows)
    out = resolve_path(cfg["extraction"]["ledger_path"])
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    logger.info(
        "Ledger: %d invoices, %d with findings -> %s",
        len(df),
        int((df["n_findings"] > 0).sum()),
        out,
    )
    return df


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    process_corpus()
