"""Policy RAG with a stub embedder and FakeProvider (no model downloads)."""

import hashlib
import re

import numpy as np
import pytest

import ledgerlens.rag.qa as qa
from ledgerlens.llm.base import FakeProvider
from ledgerlens.rag.policies import POLICIES
from ledgerlens.settings import get_config


class _StubEmbedder:
    def embed(self, texts):
        for text in texts:
            vec = np.zeros(48, dtype=np.float32)
            for token in re.findall(r"[a-z0-9]+", text.lower()):
                vec[int(hashlib.md5(token.encode()).hexdigest(), 16) % 48] += 1.0
            yield vec


@pytest.fixture(autouse=True)
def policy_kb(tmp_path, monkeypatch):
    cfg = get_config()
    original = cfg["rag"]["policy_dir"]
    kb = tmp_path / "policies"
    kb.mkdir()
    for name, text in POLICIES.items():
        (kb / name).write_text(text, encoding="utf-8")
    cfg["rag"]["policy_dir"] = str(kb)

    import fastembed

    monkeypatch.setattr(fastembed, "TextEmbedding", lambda *a, **k: _StubEmbedder())
    qa.invalidate_index()
    yield
    cfg["rag"]["policy_dir"] = original
    qa.invalidate_index()


def test_retrieve_finds_relevant_policy():
    hits = qa.retrieve("What payment terms are acceptable for suppliers?")
    assert hits
    assert any(h.doc == "expense-policy" for h in hits)


def test_retrieve_tax_question_hits_tax_policy():
    hits = qa.retrieve("What VAT rate applies in Germany?")
    assert any(h.doc == "tax-policy" for h in hits)


def test_ask_grounds_prompt_and_cites():
    provider = FakeProvider(canned="Terms over 60 days need CFO approval [expense-policy].")
    result = qa.ask("Can we accept 90-day terms?", provider=provider)
    assert result["provider"] == "fake"
    assert result["sources"]
    sent = provider.calls[0]["prompt"]
    assert "Policy excerpts" in sent
    assert "90-day terms" in sent
