"""Synthetic invoice corpus: realistic PDFs + ground-truth JSON.

A configurable fraction carries injected bookkeeping errors (bad arithmetic,
implausible tax, duplicate invoice numbers, overdue terms) so the validation
engine has real work; ground truth records both fields and injected errors.

Usage:
    python -m ledgerlens.corpus.generate
"""

from __future__ import annotations

import json
import logging
import random
from datetime import date, timedelta

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from ledgerlens.settings import get_config, resolve_path

logger = logging.getLogger(__name__)

VENDORS = [
    ("Northwind Traders", "US", 0.0825),
    ("Contoso Ltd", "UK", 0.20),
    ("Fabrikam Inc", "US", 0.0725),
    ("Tailspin Toys", "DE", 0.19),
    ("Wingtip Supplies", "US", 0.0),
    ("Proseware GmbH", "DE", 0.19),
    ("Litware Services", "UK", 0.20),
    ("Adventure Works", "CA", 0.13),
]
ITEMS = [
    ("Industrial pump unit", 180, 2400),
    ("Steel fastener pack", 8, 90),
    ("Hydraulic hose 5m", 25, 160),
    ("Control valve assembly", 90, 800),
    ("Bearing kit", 30, 240),
    ("Software license (annual)", 120, 1500),
    ("Maintenance visit", 150, 900),
    ("Safety gloves box", 12, 45),
]


def _make_invoice(i: int, rng: random.Random) -> dict:
    vendor, country, tax_rate = rng.choice(VENDORS)
    inv_date = date(2026, 1, 1) + timedelta(days=rng.randint(0, 180))
    due_date = inv_date + timedelta(days=rng.choice([14, 30, 45, 60]))
    n_lines = rng.randint(1, 5)
    lines = []
    for _ in range(n_lines):
        name, lo, hi = rng.choice(ITEMS)
        qty = rng.randint(1, 6)
        price = round(rng.uniform(lo, hi), 2)
        lines.append(
            {"description": name, "qty": qty, "unit_price": price, "amount": round(qty * price, 2)}
        )
    subtotal = round(sum(line["amount"] for line in lines), 2)
    tax = round(subtotal * tax_rate, 2)
    total = round(subtotal + tax, 2)
    return {
        "invoice_no": f"INV-{2026}{i:04d}",
        "vendor": vendor,
        "country": country,
        "invoice_date": inv_date.isoformat(),
        "due_date": due_date.isoformat(),
        "lines": lines,
        "subtotal": subtotal,
        "tax_rate": tax_rate,
        "tax": tax,
        "total": total,
        "errors": [],
    }


def _inject_error(inv: dict, rng: random.Random, used_numbers: list[str]) -> None:
    kind = rng.choice(["bad_total", "bad_subtotal", "crazy_tax", "duplicate_no", "overdue_terms"])
    if kind == "bad_total":
        inv["total"] = round(inv["total"] + rng.choice([-1, 1]) * rng.uniform(5, 80), 2)
    elif kind == "bad_subtotal":
        inv["subtotal"] = round(inv["subtotal"] + rng.uniform(3, 40), 2)
        inv["total"] = round(inv["subtotal"] + inv["tax"], 2)
    elif kind == "crazy_tax":
        inv["tax"] = round(inv["subtotal"] * rng.uniform(0.45, 0.8), 2)
        inv["total"] = round(inv["subtotal"] + inv["tax"], 2)
    elif kind == "duplicate_no" and used_numbers:
        inv["invoice_no"] = rng.choice(used_numbers)
    elif kind == "overdue_terms":
        inv["due_date"] = (
            date.fromisoformat(inv["invoice_date"]) + timedelta(days=400)
        ).isoformat()
    inv["errors"].append(kind)


def render_pdf(inv: dict, path) -> None:
    c = canvas.Canvas(str(path), pagesize=letter)
    y = 740
    c.setFont("Helvetica-Bold", 16)
    c.drawString(72, y, inv["vendor"])
    c.setFont("Helvetica", 10)
    y -= 18
    c.drawString(72, y, f"Country: {inv['country']}")
    y -= 30
    c.setFont("Helvetica-Bold", 12)
    c.drawString(72, y, f"Invoice Number: {inv['invoice_no']}")
    c.setFont("Helvetica", 10)
    y -= 16
    c.drawString(72, y, f"Invoice Date: {inv['invoice_date']}")
    y -= 14
    c.drawString(72, y, f"Due Date: {inv['due_date']}")
    y -= 28
    c.setFont("Helvetica-Bold", 10)
    c.drawString(72, y, "Description")
    c.drawString(320, y, "Qty")
    c.drawString(370, y, "Unit Price")
    c.drawString(460, y, "Amount")
    c.setFont("Helvetica", 10)
    for line in inv["lines"]:
        y -= 16
        c.drawString(72, y, line["description"])
        c.drawString(320, y, str(line["qty"]))
        c.drawString(370, y, f"{line['unit_price']:.2f}")
        c.drawString(460, y, f"{line['amount']:.2f}")
    y -= 24
    c.drawString(370, y, "Subtotal:")
    c.drawString(460, y, f"{inv['subtotal']:.2f}")
    y -= 14
    c.drawString(370, y, "Tax:")
    c.drawString(460, y, f"{inv['tax']:.2f}")
    y -= 14
    c.setFont("Helvetica-Bold", 11)
    c.drawString(370, y, "Total Due:")
    c.drawString(460, y, f"{inv['total']:.2f}")
    c.showPage()
    c.save()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = get_config()["corpus"]
    rng = random.Random(cfg["seed"])
    pdf_dir = resolve_path(cfg["pdf_dir"])
    truth_dir = resolve_path(cfg["truth_dir"])
    pdf_dir.mkdir(parents=True, exist_ok=True)
    truth_dir.mkdir(parents=True, exist_ok=True)

    used_numbers: list[str] = []
    n_errors = 0
    for i in range(1, cfg["n_invoices"] + 1):
        inv = _make_invoice(i, rng)
        if rng.random() < cfg["error_rate"]:
            _inject_error(inv, rng, used_numbers)
            n_errors += 1
        used_numbers.append(inv["invoice_no"])
        stem = f"invoice_{i:04d}"
        render_pdf(inv, pdf_dir / f"{stem}.pdf")
        (truth_dir / f"{stem}.json").write_text(json.dumps(inv, indent=1), encoding="utf-8")
    logger.info(
        "Generated %d invoices (%d with injected errors) -> %s",
        cfg["n_invoices"],
        n_errors,
        pdf_dir,
    )


if __name__ == "__main__":
    main()
