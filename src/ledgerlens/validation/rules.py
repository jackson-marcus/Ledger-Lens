"""Validation rules engine: pure, ordered, explainable checks on extractions.

Every rule returns findings with severity + human-readable explanation; the
engine also cross-checks the whole ledger (duplicate invoice numbers)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ledgerlens.extraction.extract import ExtractedInvoice
from ledgerlens.settings import get_config


@dataclass
class Finding:
    rule: str
    severity: str  # error | warning
    message: str

    def as_dict(self) -> dict:
        return vars(self)


def _num(v) -> float | None:
    return v if isinstance(v, int | float) else None


def check_arithmetic(inv: ExtractedInvoice) -> list[Finding]:
    cfg = get_config()["validation"]
    tol = cfg["amount_tolerance"]
    findings = []
    subtotal, tax, total = _num(inv.get("subtotal")), _num(inv.get("tax")), _num(inv.get("total"))
    lines_sum = _num(inv.get("lines_sum"))

    if subtotal is not None and lines_sum is not None and abs(subtotal - lines_sum) > tol:
        findings.append(
            Finding(
                "lines_vs_subtotal",
                "error",
                f"Line items sum to {lines_sum:.2f} but subtotal reads {subtotal:.2f}",
            )
        )
    if None not in (subtotal, tax, total) and abs((subtotal + tax) - total) > tol:
        findings.append(
            Finding(
                "subtotal_plus_tax",
                "error",
                f"Subtotal {subtotal:.2f} + tax {tax:.2f} = {subtotal + tax:.2f}, but total reads {total:.2f}",
            )
        )
    return findings


def check_tax_plausibility(inv: ExtractedInvoice) -> list[Finding]:
    cfg = get_config()["validation"]
    subtotal, tax = _num(inv.get("subtotal")), _num(inv.get("tax"))
    if subtotal and tax is not None and subtotal > 0:
        rate = tax / subtotal
        if rate > cfg["max_tax_rate"]:
            return [
                Finding(
                    "tax_rate_implausible",
                    "error",
                    f"Implied tax rate {rate:.0%} exceeds plausible maximum {cfg['max_tax_rate']:.0%}",
                )
            ]
    return []


def check_dates(inv: ExtractedInvoice) -> list[Finding]:
    cfg = get_config()["validation"]
    findings = []
    try:
        issued = date.fromisoformat(str(inv.get("invoice_date")))
        due = date.fromisoformat(str(inv.get("due_date")))
    except (ValueError, TypeError):
        return [Finding("dates_unparseable", "warning", "Invoice/due date missing or unparseable")]
    if due < issued:
        findings.append(
            Finding("due_before_issue", "error", f"Due date {due} precedes invoice date {issued}")
        )
    elif (due - issued).days > cfg["due_days_max"]:
        findings.append(
            Finding(
                "terms_unusual",
                "warning",
                f"Payment terms of {(due - issued).days} days exceed {cfg['due_days_max']}-day policy",
            )
        )
    return findings


def check_required_fields(inv: ExtractedInvoice) -> list[Finding]:
    missing = [k for k in ("invoice_no", "vendor", "total") if inv.get(k) in (None, "")]
    if missing:
        return [
            Finding("missing_fields", "error", f"Missing required fields: {', '.join(missing)}")
        ]
    return []


def check_duplicates(inv: ExtractedInvoice, seen_numbers: dict[str, str]) -> list[Finding]:
    """seen_numbers: invoice_no -> file of first occurrence."""
    number = inv.get("invoice_no")
    if number and number in seen_numbers and seen_numbers[number] != inv.file:
        return [
            Finding(
                "duplicate_invoice_no",
                "error",
                f"Invoice number {number} already seen in {seen_numbers[number]}",
            )
        ]
    return []


def validate_invoice(
    inv: ExtractedInvoice, seen_numbers: dict[str, str] | None = None
) -> list[Finding]:
    findings = (
        check_required_fields(inv)
        + check_arithmetic(inv)
        + check_tax_plausibility(inv)
        + check_dates(inv)
    )
    if seen_numbers is not None:
        findings += check_duplicates(inv, seen_numbers)
        number = inv.get("invoice_no")
        if number:
            seen_numbers.setdefault(number, inv.file)
    return findings
