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
    findings, truth = _findings_for(make_pdf, 12, error="crazy_tax")
    assert any(f.rule == "tax_rate_implausible" for f in findings)


def test_overdue_terms_flagged(make_pdf):
    findings, truth = _findings_for(make_pdf, 13, error="overdue_terms")
    assert any(f.rule == "terms_unusual" for f in findings)


def test_duplicate_numbers_caught(make_pdf):
    path_a, _ = make_pdf(20)
    path_b, _ = make_pdf(21)
    inv_a = extract_pdf(path_a)
    inv_b = extract_pdf(path_b)
    inv_b.fields["invoice_no"] = inv_a.fields["invoice_no"]
    seen: dict[str, str] = {}
    assert not any(f.rule == "duplicate_invoice_no" for f in validate_invoice(inv_a, seen))
    assert any(f.rule == "duplicate_invoice_no" for f in validate_invoice(inv_b, seen))
