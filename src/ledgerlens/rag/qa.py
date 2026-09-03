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

RRF_K = 60


@dataclass
class PolicyChunk:
    doc: str
    text: str
    section: str = ""


@dataclass
class Hit:
    """One retrieved chunk plus where it ranked in each retriever.

    `dense_rank` / `bm25_rank` are 0-based positions in the respective ranked
    lists (over all chunks); `bm25_score` of 0 means the query shares no token
    with the chunk at all, which the grounding gate uses as a red flag.
    """

    chunk: PolicyChunk
    fused: float
    dense_rank: int
    bm25_rank: int
    bm25_score: float
    dense_score: float  # cosine similarity between query and chunk embeddings
    bm25_margin: float  # this chunk's BM25 score over the best BM25 score of any other chunk
    coverage: float  # fraction of the query's distinct tokens that appear in the chunk


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
            heading, _, body = block.partition("\n")
            section = heading.lstrip("#").strip()
            if not body.strip():
                continue  # a bare document title carries nothing worth retrieving
            for start in range(0, len(block), size):
                piece = block[start : start + size].strip()
                if piece:
                    chunks.append(PolicyChunk(doc=path.stem, text=piece, section=section))
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


def _margin(scores: np.ndarray, i: int, cap: float = 100.0) -> float:
    others = np.delete(scores, i)
    best_other = float(others.max()) if others.size else 0.0
    if best_other <= 0.0:
        return cap if scores[i] > 0.0 else 0.0
    return min(cap, float(scores[i]) / best_other)


def _coverage(query_tokens: list[str], text: str) -> float:
    wanted = set(query_tokens)
    if not wanted:
        return 0.0
    present = wanted & set(_tokenize(text))
    return len(present) / len(wanted)


def retrieve_hits(question: str, top_k: int | None = None) -> list[Hit]:
    cfg = get_config()["rag"]
    top_k = top_k or cfg["top_k"]
    chunks, dense, bm25, model = _index()

    q = np.asarray(next(iter(model.embed([question]))), dtype=np.float32)
    q /= np.linalg.norm(q) + 1e-12
    cosines = dense @ q
    dense_order = np.argsort(-cosines, kind="stable")
    q_tokens = _tokenize(question)
    bm25_scores = np.asarray(bm25.get_scores(q_tokens), dtype=np.float64)
    bm25_order = np.argsort(-bm25_scores, kind="stable")
    dense_rank = {int(idx): r for r, idx in enumerate(dense_order)}
    bm25_rank = {int(idx): r for r, idx in enumerate(bm25_order)}

    fused: dict[int, float] = {}
    for rank_list in (dense_order[: top_k * 3], bm25_order[: top_k * 3]):
        for rank, idx in enumerate(rank_list):
            fused[int(idx)] = fused.get(int(idx), 0.0) + 1.0 / (RRF_K + rank + 1)
    best = sorted(fused, key=fused.get, reverse=True)[:top_k]
    return [
        Hit(
            chunk=chunks[i],
            fused=fused[i],
            dense_rank=dense_rank[i],
            bm25_rank=bm25_rank[i],
            bm25_score=float(bm25_scores[i]),
            dense_score=float(cosines[i]),
            bm25_margin=_margin(bm25_scores, i),
            coverage=_coverage(q_tokens, chunks[i].text),
        )
        for i in best
    ]


def retrieve(question: str, top_k: int | None = None) -> list[PolicyChunk]:
    return [h.chunk for h in retrieve_hits(question, top_k)]


def build_prompt(question: str, hits: list[PolicyChunk]) -> str:
    context = "\n\n".join(f"--- [{h.doc}] ---\n{h.text}" for h in hits)
    return PROMPT.format(context=context, question=question)


def sources(hits: list[PolicyChunk]) -> list[dict]:
    return [{"doc": h.doc, "section": h.section, "preview": h.text[:200]} for h in hits]


def ask(question: str, provider: LLMProvider | None = None) -> dict:
    provider = provider or get_provider()
    hits = retrieve(question)
    answer = provider.complete(
        build_prompt(question, hits),
        system=SYSTEM,
        max_tokens=get_config()["rag"]["max_answer_tokens"],
    )
    return {"answer": answer, "provider": provider.name, "sources": sources(hits)}
