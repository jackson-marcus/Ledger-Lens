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
        # Rebuild from scratch on every draw: clearing only the error list
        # left earlier injections' mutations in place, so fixtures asking for
        # one error kind could carry two or three.
        while error and error not in inv["errors"]:
            inv = _make_invoice(seed, rng)
            _inject_error(inv, rng, ["INV-20260001"])
        path = tmp_path / f"inv_{seed}.pdf"
        render_pdf(inv, path)
        return path, inv

    return _make


class _StubEmbedder:
    """Hash-projected bag of words: deterministic, offline, no model download."""

    def embed(self, texts):
        import hashlib
        import re

        import numpy as np

        for text in texts:
            vec = np.zeros(48, dtype=np.float32)
            for token in re.findall(r"[a-z0-9]+", text.lower()):
                vec[int(hashlib.md5(token.encode()).hexdigest(), 16) % 48] += 1.0
            yield vec


@pytest.fixture()
def policy_kb(tmp_path, monkeypatch):
    """Policy docs written to a temp dir and indexed with the stub embedder.

    Yields the directory so a test can edit the policies and re-index.
    """
    import fastembed

    import ledgerlens.rag.qa as qa
    from ledgerlens.rag.policies import POLICIES
    from ledgerlens.settings import get_config

    cfg = get_config()
    original = cfg["rag"]["policy_dir"]
    kb = tmp_path / "policies"
    kb.mkdir()
    for name, text in POLICIES.items():
        (kb / name).write_text(text, encoding="utf-8")
    cfg["rag"]["policy_dir"] = str(kb)
    monkeypatch.setattr(fastembed, "TextEmbedding", lambda *a, **k: _StubEmbedder())
    qa.invalidate_index()
    yield kb
    cfg["rag"]["policy_dir"] = original
    qa.invalidate_index()
