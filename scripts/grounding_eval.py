"""Measure finding-to-policy grounding: query strategy x citation gate.

Builds a labelled set end to end (synthetic invoices carrying every injected
error kind plus hand-broken ones, rendered to PDF, extracted, validated), then
asks the grounding layer for each finding's governing clause and scores it
against the expected (doc, section). Two failure modes are scored separately:

  * a finding with no governing clause gets one anyway (false citation), and
  * the governing clause has been removed from the policy docs, so retrieval
    can only return something unrelated (the "clause removed" ablation).

Run:
    uv run python scripts/grounding_eval.py [--n 240] [--verbose]
"""

from __future__ import annotations

import argparse
import random
import tempfile
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

from ledgerlens.corpus.generate import _inject_error, _make_invoice, render_pdf
from ledgerlens.extraction.extract import extract_pdf
from ledgerlens.gateway import grounding
from ledgerlens.rag import qa
from ledgerlens.rag.policies import POLICIES
from ledgerlens.settings import get_config
from ledgerlens.validation.rules import Finding, validate_invoice

EXPECTED: dict[str, tuple[str, str] | None] = {
    "lines_vs_subtotal": ("vendor-policy", "Dispute process"),
    "subtotal_plus_tax": ("vendor-policy", "Dispute process"),
    "tax_rate_implausible": ("tax-policy", "Plausible tax rates"),
    "terms_unusual": ("expense-policy", "Payment terms"),
    "terms_unacceptable": ("expense-policy", "Payment terms"),
    "due_before_issue": ("expense-policy", "Payment terms"),
    "duplicate_invoice_no": ("expense-policy", "Duplicate handling"),
    "missing_fields": None,
    "dates_unparseable": None,
}
GATES: tuple[grounding.Gate, ...] = ("none", "lexical", "agree", "margin", "coverage")
BREAKS = ["missing_no", "bad_due_date", "due_before_issue", "terms_90"]


def _break(inv: dict, kind: str) -> None:
    issued = date.fromisoformat(inv["invoice_date"])
    if kind == "missing_no":
        inv["invoice_no"] = ""
    elif kind == "bad_due_date":
        inv["due_date"] = "TBD"
    elif kind == "due_before_issue":
        inv["due_date"] = (issued - timedelta(days=10)).isoformat()
    elif kind == "terms_90":
        inv["due_date"] = (issued + timedelta(days=90)).isoformat()
    inv["errors"].append(kind)


def build_findings(n: int, seed: int, workdir: Path) -> list[Finding]:
    rng = random.Random(seed)
    used: list[str] = []
    seen: dict[str, str] = {}
    findings: list[Finding] = []
    workdir.mkdir(parents=True, exist_ok=True)
    for i in range(1, n + 1):
        inv = _make_invoice(i, rng)
        slot = i % 3
        if slot == 0:
            _inject_error(inv, rng, used)
        elif slot == 1:
            _break(inv, BREAKS[(i // 3) % len(BREAKS)])
        used.append(inv["invoice_no"])
        path = workdir / f"inv_{i:04d}.pdf"
        render_pdf(inv, path)
        findings.extend(validate_invoice(extract_pdf(path), seen))
    return findings


def write_kb(kb: Path, drop: tuple[str, str] | None = None) -> None:
    """Write the policy docs, optionally with one `## section` removed."""
    kb.mkdir(parents=True, exist_ok=True)
    for name, text in POLICIES.items():
        if drop and name == f"{drop[0]}.md":
            blocks = text.split("\n## ")
            blocks = [b for b in blocks if not b.startswith(drop[1])]
            text = "\n## ".join(blocks)
        (kb / name).write_text(text, encoding="utf-8")
    qa.invalidate_index()


def query_for(f: Finding, style: str) -> str | None:
    return f.message if style == "message" else grounding.POLICY_QUERIES.get(f.rule)


def score(findings: list[Finding], style: str, gate: grounding.Gate) -> dict:
    per_rule: dict[str, Counter] = defaultdict(Counter)
    for f in findings:
        query = query_for(f, style)
        got = (
            grounding.ground_query(query, gate=gate)
            if query
            else grounding.Grounding(None, "unmapped")
        )
        expected = EXPECTED[f.rule]
        if expected is None:
            per_rule[f.rule]["false_cite" if got.ref else "ok"] += 1
        elif got.ref is None:
            per_rule[f.rule]["gated"] += 1
        elif (got.ref.doc, got.ref.section) == expected:
            per_rule[f.rule]["ok"] += 1
        else:
            per_rule[f.rule]["wrong"] += 1
    n_with = sum(1 for f in findings if EXPECTED[f.rule] is not None)
    n_without = len(findings) - n_with
    ok_with = sum(c["ok"] for r, c in per_rule.items() if EXPECTED[r] is not None)
    false_cites = sum(c["false_cite"] for r, c in per_rule.items() if EXPECTED[r] is None)
    return {
        "precision": ok_with / max(n_with, 1),
        "false_cite": false_cites / max(n_without, 1),
        "accuracy": sum(c["ok"] for c in per_rule.values()) / max(len(findings), 1),
        "per_rule": per_rule,
    }


def clause_removed(kb: Path, findings: list[Finding]) -> dict[grounding.Gate, tuple[int, int]]:
    """For each rule with a clause, delete that clause and count wrong citations."""
    rules = sorted({f.rule for f in findings if EXPECTED[f.rule] is not None})
    wrong: dict[grounding.Gate, int] = dict.fromkeys(GATES, 0)
    for rule in rules:
        write_kb(kb, drop=EXPECTED[rule])
        query = grounding.POLICY_QUERIES[rule]
        for gate in GATES:
            got = grounding.ground_query(query, gate=gate)
            if got.ref is not None:
                wrong[gate] += 1
    write_kb(kb)
    return {gate: (wrong[gate], len(rules)) for gate in GATES}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=240)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    cfg = get_config()["rag"]
    original_dir = cfg["policy_dir"]
    with tempfile.TemporaryDirectory() as tmp:
        findings = build_findings(args.n, args.seed, Path(tmp) / "pdfs")
        kb = Path(tmp) / "policies"
        cfg["policy_dir"] = str(kb)
        write_kb(kb)
        counts = Counter(f.rule for f in findings)
        print(f"{len(findings)} findings from {args.n} invoices: {dict(counts)}\n")
        print(f"{'query':<9} {'gate':<8} {'precision':>10} {'false-cite':>11} {'accuracy':>9}")
        for style in ("message", "curated"):
            for gate in GATES:
                r = score(findings, style, gate)
                print(
                    f"{style:<9} {gate:<8} {r['precision']:>10.1%} "
                    f"{r['false_cite']:>11.1%} {r['accuracy']:>9.1%}"
                )
                if args.verbose:
                    for rule, c in sorted(r["per_rule"].items()):
                        print(f"    {rule:<22} {dict(c)}")
        print("\nclause removed from the policy docs (curated query) -> still cites something:")
        for gate, (n_wrong, n_rules) in clause_removed(kb, findings).items():
            print(f"  gate={gate:<8} {n_wrong}/{n_rules} rules wrongly cited")
        cfg["policy_dir"] = original_dir
        qa.invalidate_index()


if __name__ == "__main__":
    main()
