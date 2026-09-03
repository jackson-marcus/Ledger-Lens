"""Findings -> policy clause, including the cases where citing is wrong."""

from ledgerlens.gateway import grounding
from ledgerlens.rag import qa
from ledgerlens.validation.rules import RULE_IDS, Finding


def test_every_rule_is_either_grounded_or_deliberately_not():
    declared = set(grounding.POLICY_QUERIES) | set(grounding.UNGROUNDED_RULES)
    assert set(RULE_IDS) == declared
    assert not (set(grounding.POLICY_QUERIES) & grounding.UNGROUNDED_RULES)


def test_duplicate_finding_cites_the_duplicate_handling_clause(policy_kb):
    f = Finding("duplicate_invoice_no", "error", "Invoice number INV-1 already seen in a.pdf")
    g = grounding.ground_finding(f)
    assert g.outcome == "cited"
    assert (g.ref.doc, g.ref.section) == ("expense-policy", "Duplicate handling")
    assert "review queue" in g.ref.excerpt


def test_arithmetic_finding_is_not_pulled_towards_the_tax_policy(policy_kb):
    f = Finding(
        "subtotal_plus_tax", "error", "Subtotal 100.00 + tax 8.00 = 108.00, but total reads 150.00"
    )
    g = grounding.ground_finding(f)
    assert (g.ref.doc, g.ref.section) == ("vendor-policy", "Dispute process")


def test_rules_without_a_governing_clause_get_no_citation(policy_kb):
    f = Finding("missing_fields", "error", "Missing required fields: invoice_no, vendor, total")
    g = grounding.ground_finding(f)
    assert g.outcome == "unmapped" and g.ref is None
    # ...even though retrieval with an open gate would happily cite something.
    assert grounding.ground_query(f.message, gate="none").ref is not None


def test_removed_clause_is_refused_rather_than_replaced(policy_kb):
    doc = policy_kb / "expense-policy.md"
    blocks = doc.read_text(encoding="utf-8").split("\n## ")
    doc.write_text("\n## ".join(b for b in blocks if not b.startswith("Duplicate handling")))
    qa.invalidate_index()

    f = Finding("duplicate_invoice_no", "error", "Invoice number INV-1 already seen in a.pdf")
    assert grounding.ground_finding(f).outcome == "gated"
    ungated = grounding.ground_finding(f, gate="none")
    assert ungated.ref is not None and ungated.ref.section != "Duplicate handling"
