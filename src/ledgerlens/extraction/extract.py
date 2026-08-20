"""Field extraction from invoice PDFs: layered patterns with confidence scores.

Each field is extracted by an ordered list of strategies; confidence reflects
which strategy matched (labeled anchor > positional heuristic > fallback).
Field-level accuracy is measured against ground truth by the eval module —
extraction is honest work, not a solved regex.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from pypdf import PdfReader


@dataclass
class FieldValue:
    value: str | float | None
    confidence: float
    source: str = ""


@dataclass
class ExtractedInvoice:
    file: str
    fields: dict[str, FieldValue] = field(default_factory=dict)

    def get(self, name: str):
        fv = self.fields.get(name)
        return None if fv is None else fv.value

    def as_dict(self) -> dict:
        return {
            "file": self.file,
            "fields": {
                k: {"value": v.value, "confidence": v.confidence, "source": v.source}
                for k, v in self.fields.items()
            },
        }


MONEY = r"([0-9][0-9,]*\.[0-9]{2})"
DATE = r"(\d{4}-\d{2}-\d{2})"


def _money(text: str) -> float | None:
    try:
        return float(text.replace(",", ""))
    except (ValueError, AttributeError):
        return None


def _anchored(text: str, anchors: list[str], pattern: str) -> tuple[str | None, str | None]:
    for anchor in anchors:
        m = re.search(rf"{anchor}\s*:?\s*{pattern}", text, re.IGNORECASE)
        if m:
            return m.group(1), anchor
    return None, None


def extract_text(pdf_path) -> str:
    reader = PdfReader(str(pdf_path))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def extract_fields(text: str, file: str = "") -> ExtractedInvoice:
    inv = ExtractedInvoice(file=file)

    raw, anchor = _anchored(
        text, ["Invoice Number", "Invoice No", "Inv #"], r"([A-Z]{2,4}-?\d{4,10})"
    )
    inv.fields["invoice_no"] = FieldValue(raw, 0.95 if anchor else 0.0, anchor or "none")

    raw, anchor = _anchored(text, ["Invoice Date", "Date of Issue", "Issued"], DATE)
    inv.fields["invoice_date"] = FieldValue(raw, 0.9 if anchor else 0.0, anchor or "none")

    raw, anchor = _anchored(text, ["Due Date", "Payment Due", "Due"], DATE)
    inv.fields["due_date"] = FieldValue(raw, 0.9 if anchor else 0.0, anchor or "none")

    for name, anchors in [
        ("subtotal", ["Subtotal", "Sub-total", "Net"]),
        ("tax", ["Tax", "VAT", "GST", "Sales Tax"]),
        ("total", ["Total Due", "Total Amount", "Amount Due", "Total"]),
    ]:
        raw, anchor = _anchored(text, anchors, MONEY)
        value = _money(raw)
        confidence = 0.9 if anchor and value is not None else 0.0
        # Fallback: the largest money value on the page is usually the total.
        if name == "total" and value is None:
            candidates = [_money(m) for m in re.findall(MONEY, text)]
            candidates = [c for c in candidates if c is not None]
            if candidates:
                value, confidence, anchor = max(candidates), 0.45, "max-amount-heuristic"
        inv.fields[name] = FieldValue(value, confidence, anchor or "none")

    # Vendor: first non-empty line that isn't a labeled field.
    vendor, confidence = None, 0.0
    for line in text.splitlines():
        candidate = line.strip()
        if candidate and not re.match(
            r"(invoice|date|due|country|subtotal|tax|total)", candidate, re.IGNORECASE
        ):
            vendor, confidence = candidate, 0.7
            break
    inv.fields["vendor"] = FieldValue(vendor, confidence, "first-line-heuristic")

    # Line items: qty + unit price + amount rows.
    lines = []
    for m in re.finditer(rf"^(.+?)\s+(\d+)\s+{MONEY}\s+{MONEY}\s*$", text, re.MULTILINE):
        lines.append(
            {
                "description": m.group(1).strip(),
                "qty": int(m.group(2)),
                "unit_price": _money(m.group(3)),
                "amount": _money(m.group(4)),
            }
        )
    inv.fields["n_lines"] = FieldValue(len(lines), 0.8 if lines else 0.3, "row-pattern")
    inv.fields["lines_sum"] = FieldValue(
        round(sum(line["amount"] for line in lines), 2) if lines else None,
        0.8 if lines else 0.0,
        "row-pattern",
    )
    return inv


def extract_pdf(pdf_path) -> ExtractedInvoice:
    return extract_fields(extract_text(pdf_path), file=str(pdf_path))
