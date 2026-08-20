"""Fixtures: in-memory invoices + rendered PDFs, no network or model downloads."""

from __future__ import annotations

import random

import pytest

from ledgerlens.corpus.generate import _inject_error, _make_invoice, render_pdf


@pytest.fixture()
def clean_invoice():
    return _make_invoice(1, random.Random(1))


@pytest.fixture()
def bad_total_invoice():
    rng = random.Random(2)
    inv = _make_invoice(2, rng)
    inv["total"] = round(inv["total"] + 42.0, 2)
    inv["errors"].append("bad_total")
    return inv


@pytest.fixture()
def invoice_pdf(tmp_path, clean_invoice):
    path = tmp_path / "inv.pdf"
    render_pdf(clean_invoice, path)
    return path, clean_invoice


@pytest.fixture()
def make_pdf(tmp_path):
    def _make(seed: int, error: str | None = None):
        rng = random.Random(seed)
        inv = _make_invoice(seed, rng)
        if error:
            while error not in inv["errors"]:
                inv["errors"].clear()
                _inject_error(inv, rng, ["INV-20260001"])
        path = tmp_path / f"inv_{seed}.pdf"
        render_pdf(inv, path)
        return path, inv

    return _make
