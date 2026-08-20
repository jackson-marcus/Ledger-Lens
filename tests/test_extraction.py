"""Extraction accuracy on rendered synthetic invoices."""

from ledgerlens.extraction.extract import extract_pdf


def test_core_fields_extracted(invoice_pdf):
    path, truth = invoice_pdf
    inv = extract_pdf(path)
    assert inv.get("invoice_no") == truth["invoice_no"]
    assert inv.get("vendor") == truth["vendor"]
    assert inv.get("invoice_date") == truth["invoice_date"]
    assert inv.get("due_date") == truth["due_date"]


def test_amounts_extracted(invoice_pdf):
    path, truth = invoice_pdf
    inv = extract_pdf(path)
    assert abs(inv.get("subtotal") - truth["subtotal"]) < 0.01
    assert abs(inv.get("tax") - truth["tax"]) < 0.01
    assert abs(inv.get("total") - truth["total"]) < 0.01


def test_line_items_parsed(invoice_pdf):
    path, truth = invoice_pdf
    inv = extract_pdf(path)
    assert inv.get("n_lines") == len(truth["lines"])
    assert abs(inv.get("lines_sum") - truth["subtotal"]) < 0.01


def test_confidence_reported(invoice_pdf):
    path, _ = invoice_pdf
    inv = extract_pdf(path)
    for name in ("invoice_no", "total"):
        assert 0.0 < inv.fields[name].confidence <= 1.0


def test_missing_fields_get_zero_confidence():
    from ledgerlens.extraction.extract import extract_fields

    inv = extract_fields("just some unrelated text with 12.34 in it", file="x")
    assert inv.fields["invoice_no"].confidence == 0.0
    # Total falls back to the max-amount heuristic with reduced confidence.
    assert inv.fields["total"].source == "max-amount-heuristic"
    assert inv.fields["total"].confidence < 0.6
