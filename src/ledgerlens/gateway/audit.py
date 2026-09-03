"""One invoice, end to end: parse the PDF, run the validators, tie each
finding to policy, and say which fields a human still has to look at.

This is the code path behind POST /audit (and /extract, which stops before
the grounding stage). Each stage is timed and reported in the response so a
slow audit can be attributed to PDF parsing versus policy retrieval.
"""

from __future__ import annotations

from pathlib import Path

from ledgerlens.extraction.extract import ExtractedInvoice, extract_pdf
from ledgerlens.gateway.grounding import DEFAULT_GATE, Gate, ground_finding
from ledgerlens.observability.metrics import REGISTRY
from ledgerlens.observability.tracer import StageTrace
from ledgerlens.settings import get_config
from ledgerlens.validation.rules import Finding, validate_invoice


def review_fields(inv: ExtractedInvoice) -> list[str]:
    floor = get_config()["extraction"]["min_confidence_flag"]
    return [name for name, fv in inv.fields.items() if fv.confidence < floor]


def audit_invoice(
    pdf_path: Path,
    display_name: str | None = None,
    *,
    ground: bool = True,
    gate: Gate = DEFAULT_GATE,
    seen_numbers: dict[str, str] | None = None,
) -> dict:
    trace = StageTrace()

    with trace.stage("extract") as span:
        inv = extract_pdf(pdf_path)
        inv.file = display_name or Path(pdf_path).name
        review = review_fields(inv)
        for name in review:
            REGISTRY.inc("ledgerlens_review_fields_total", field=name)
        span.detail["review_fields"] = len(review)

    with trace.stage("validate") as span:
        findings: list[Finding] = validate_invoice(inv, seen_numbers)
        for f in findings:
            REGISTRY.inc("ledgerlens_findings_total", rule=f.rule, severity=f.severity)
        span.detail["findings"] = len(findings)

    grounded: list[dict] = []
    if ground:
        with trace.stage("ground") as span:
            cited = 0
            for f in findings:
                g = ground_finding(f, gate=gate)
                REGISTRY.inc("ledgerlens_grounding_total", outcome=g.outcome)
                cited += g.outcome == "cited"
                grounded.append({**f.as_dict(), "policy": g.as_dict()})
            span.detail["cited"] = cited
    else:
        grounded = [f.as_dict() for f in findings]

    result = inv.as_dict()
    result["findings"] = grounded
    result["review_fields"] = review
    result["max_severity"] = max((f.severity for f in findings), default="")
    result["stages"] = trace.as_list()
    return result
