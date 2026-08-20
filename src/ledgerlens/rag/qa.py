"""Policy RAG: hybrid retrieval (fastembed dense + BM25, RRF) over policy docs,
grounded answers with [doc] citations via the swappable LLM provider."""

from __future__ import annotations

import functools
import re
from dataclasses import dataclass

import numpy as np
from rank_bm25 import BM25Okapi

from ledgerlens.llm.base import LLMProvider
from ledgerlens.llm.factory import get_provider
from ledgerlens.settings import get_config, resolve_path

SYSTEM = "You are an accounts-payable policy assistant. Answer only from the provided policy excerpts and cite them as [doc-name]. If the policies do not cover it, say so."

PROMPT = """Policy excerpts:
{context}

Question: {question}

Answer (with [doc] citations):"""


@dataclass
class PolicyChunk:
    doc: str
    text: str


def _chunks() -> list[PolicyChunk]:
    cfg = get_config()["rag"]
    policy_dir = resolve_path(cfg["policy_dir"])
    size = cfg["chunk_size"]
    chunks = []
    for path in sorted(policy_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        for block in text.split("\n## "):
            block = block.strip()
            if not block:
                continue
            for start in range(0, len(block), size):
                piece = block[start : start + size].strip()
                if piece:
                    chunks.append(PolicyChunk(doc=path.stem, text=piece))
    return chunks


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


@functools.lru_cache(maxsize=1)
def _index():
    chunks = _chunks()
    if not chunks:
        raise FileNotFoundError("No policy docs; run `python -m ledgerlens.rag.policies`")
    from fastembed import TextEmbedding

    model = TextEmbedding("sentence-transformers/all-MiniLM-L6-v2")
    dense = np.array(
        [np.asarray(v, dtype=np.float32) for v in model.embed([c.text for c in chunks])]
    )
    dense /= np.linalg.norm(dense, axis=1, keepdims=True) + 1e-12
    bm25 = BM25Okapi([_tokenize(c.text) for c in chunks])
    return chunks, dense, bm25, model


def invalidate_index() -> None:
    _index.cache_clear()


def retrieve(question: str, top_k: int | None = None) -> list[PolicyChunk]:
    cfg = get_config()["rag"]
    top_k = top_k or cfg["top_k"]
    chunks, dense, bm25, model = _index()

    q = np.asarray(next(iter(model.embed([question]))), dtype=np.float32)
    q /= np.linalg.norm(q) + 1e-12
    dense_rank = np.argsort(-(dense @ q))
    bm25_rank = np.argsort(-np.asarray(bm25.get_scores(_tokenize(question))))

    fused: dict[int, float] = {}
    for rank_list in (dense_rank[: top_k * 3], bm25_rank[: top_k * 3]):
        for rank, idx in enumerate(rank_list):
            fused[int(idx)] = fused.get(int(idx), 0.0) + 1.0 / (60 + rank + 1)
    best = sorted(fused, key=fused.get, reverse=True)[:top_k]
    return [chunks[i] for i in best]


def ask(question: str, provider: LLMProvider | None = None) -> dict:
    provider = provider or get_provider()
    hits = retrieve(question)
    context = "\n\n".join(f"--- [{h.doc}] ---\n{h.text}" for h in hits)
    answer = provider.complete(
        PROMPT.format(context=context, question=question),
        system=SYSTEM,
        max_tokens=get_config()["rag"]["max_answer_tokens"],
    )
    return {
        "answer": answer,
        "provider": provider.name,
        "sources": [{"doc": h.doc, "preview": h.text[:200]} for h in hits],
    }
