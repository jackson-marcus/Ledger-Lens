"""Validation rules on extracted invoices (rendered through the real pipeline)."""

from ledgerlens.extraction.extract import extract_pdf
from ledgerlens.validation.rules import validate_invoice


def _findings_for(make_pdf, seed, error=None):
    path, truth = make_pdf(seed, error)
    inv = extract_pdf(path)
    return validate_invoice(inv), truth


def test_clean_invoice_passes(make_pdf):
    findings, _ = _findings_for(make_pdf, 10)
    assert [f for f in findings if f.severity == "error"] == []


def test_bad_total_caught(make_pdf):
    findings, truth = _findings_for(make_pdf, 11, error="bad_total")
    assert "bad_total" in truth["errors"]
    assert any(f.rule == "subtotal_plus_tax" for f in findings)


def test_crazy_tax_caught(make_pdf):
    findings, _ = _findings_for(make_pdf, 12, error="crazy_tax")
    assert any(f.rule == "tax_rate_implausible" for f in findings)


def test_terms_past_120_days_are_an_error_not_a_warning(make_pdf):
    # The expense policy says terms beyond 120 days are never acceptable; the
    # eval harness counts injected overdue terms as errors, so a warning here
    # silently capped validation recall.
    findings, truth = _findings_for(make_pdf, 13, error="overdue_terms")
    assert "overdue_terms" in truth["errors"]
    (finding,) = [f for f in findings if f.rule.startswith("terms_")]
    assert finding.rule == "terms_unacceptable" and finding.severity == "error"
    assert "400 days" in finding.message


def test_terms_between_60_and_120_days_only_need_cfo_approval(make_pdf):
    from datetime import date, timedelta

    from ledgerlens.corpus.generate import render_pdf

    path, inv = make_pdf(14)
    inv["due_date"] = (date.fromisoformat(inv["invoice_date"]) + timedelta(days=90)).isoformat()
    render_pdf(inv, path)
    findings = validate_invoice(extract_pdf(path))
    assert [(f.rule, f.severity) for f in findings] == [("terms_unusual", "warning")]
    assert "CFO" in findings[0].message
