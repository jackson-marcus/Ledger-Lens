"""Policy RAG with a stub embedder and FakeProvider (no model downloads)."""

import pytest

import ledgerlens.rag.qa as qa
from ledgerlens.llm.base import FakeProvider


@pytest.fixture(autouse=True)
def _kb(policy_kb):
    yield


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


def test_chunks_carry_their_section_and_skip_bare_titles():
    chunks, *_ = qa._index()
    sections = {(c.doc, c.section) for c in chunks}
    assert ("expense-policy", "Duplicate handling") in sections
    assert ("capitalization-policy", "Capitalization Policy") in sections
    assert all(len(c.text.splitlines()) > 1 for c in chunks)


def test_hits_report_where_each_retriever_ranked_them():
    hits = qa.retrieve_hits("duplicate invoice number paid once review queue", top_k=3)
    top = hits[0]
    assert (top.chunk.doc, top.chunk.section) == ("expense-policy", "Duplicate handling")
    assert top.dense_rank == 0 and top.bm25_rank == 0
    assert top.bm25_score > hits[1].bm25_score
    assert top.bm25_margin > 1.0
