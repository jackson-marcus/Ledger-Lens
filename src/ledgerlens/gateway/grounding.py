"""Tie each validation finding to the policy clause that governs it.

A finding such as "implied tax rate 62% exceeds plausible maximum 30%" is only
half an answer for an accounts-payable clerk; the other half is what policy
says to do about it (escalate to the tax team). Each rule id carries a short
retrieval query written by the rule's author; the policy knowledge base is
searched with it and the top chunk is returned as the citation.

Two things can go wrong, and both are worse than returning nothing: a rule
with no governing clause (missing fields, unparseable dates) gets one anyway,
or the clause was edited out of the policy docs and retrieval quietly returns
the nearest unrelated paragraph. Rules without a query are never grounded,
and the gate refuses a citation unless the chunk actually contains at least
half of the words in the author's query. Retriever agreement and BM25 margin
gates are kept as alternatives because they were measured and lost: a single
shared word ("line", "tax") wins by default when nothing else matches at all.
Using the finding's own message as the query was measured and rejected too;
`scripts/grounding_eval.py` produces the numbers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ledgerlens.rag import qa
from ledgerlens.validation.rules import Finding

Gate = Literal["none", "lexical", "agree", "margin", "coverage"]

DEFAULT_GATE: Gate = "coverage"
MARGIN_MIN = 2.0  # margin gate: top chunk's BM25 over the runner-up chunk's
COVERAGE_MIN = 0.5  # coverage gate: share of the query's words the chunk must contain

# Rule id -> what to search the policy corpus for. Deliberately absent:
# missing_fields and dates_unparseable, which no policy document addresses.
POLICY_QUERIES: dict[str, str] = {
    "lines_vs_subtotal": "arithmetic discrepancy line items computed versus stated amounts dispute",
    "subtotal_plus_tax": "arithmetic discrepancy stated total dispute in writing",
    "tax_rate_implausible": "implied tax rate exceeds plausible maximum escalate tax team",
    "terms_unusual": "payment terms longer than 60 days CFO approval",
    "terms_unacceptable": "payment terms longer than 120 days never acceptable",
    "due_before_issue": "payment terms due date supplier net 30",
    "duplicate_invoice_no": "duplicate invoice number paid once review queue",
}
UNGROUNDED_RULES: frozenset[str] = frozenset({"missing_fields", "dates_unparseable"})


@dataclass
class PolicyRef:
    doc: str
    section: str
    excerpt: str
    query: str

    def as_dict(self) -> dict:
        return vars(self)


@dataclass
class Grounding:
    ref: PolicyRef | None
    outcome: str  # cited | gated | unmapped | no_docs

    def as_dict(self) -> dict | None:
        return None if self.ref is None else self.ref.as_dict()


def passes_gate(top: qa.Hit, gate: Gate) -> bool:
    if gate == "none":
        return True
    if gate == "lexical":
        return top.bm25_score > 0.0
    if gate == "coverage":
        return top.coverage >= COVERAGE_MIN
    agrees = top.dense_rank == 0 and top.bm25_rank == 0
    if gate == "agree":
        return agrees
    return agrees and top.bm25_margin >= MARGIN_MIN


def ground_query(query: str, gate: Gate = DEFAULT_GATE) -> Grounding:
    try:
        hits = qa.retrieve_hits(query, top_k=3)
    except FileNotFoundError:
        return Grounding(None, "no_docs")
    if not hits:
        return Grounding(None, "no_docs")
    top = hits[0]
    if not passes_gate(top, gate):
        return Grounding(None, "gated")
    ref = PolicyRef(
        doc=top.chunk.doc, section=top.chunk.section, excerpt=top.chunk.text, query=query
    )
    return Grounding(ref, "cited")


def ground_finding(finding: Finding, gate: Gate = DEFAULT_GATE) -> Grounding:
    query = POLICY_QUERIES.get(finding.rule)
    if query is None:
        return Grounding(None, "unmapped")
    return ground_query(query, gate=gate)
