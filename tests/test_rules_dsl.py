"""Unit tests for the Declarative Rules Engine DSL and AST Interpreter."""

from ledgerlens.rules_engine.ast_nodes import (
    BinaryOp,
    FieldRef,
    RuleNode,
)
from ledgerlens.rules_engine.engine import DeclarativeRulesEngine
from ledgerlens.rules_engine.interpreter import ASTInterpreter


def test_interpreter_arithmetic():
    interp = ASTInterpreter(tolerance=0.01)
    ctx = {"a": 10.0, "b": 5.0, "c": 15.0}

    # a + b == c
    expr = BinaryOp("==", BinaryOp("+", FieldRef("a"), FieldRef("b")), FieldRef("c"))
    assert interp.eval(expr, ctx) is True


def test_interpreter_null_safe_eval():
    interp = ASTInterpreter(tolerance=0.01)
    ctx = {"a": 10.0, "b": None}

    # a + b should return None gracefully without throwing
    expr = BinaryOp("+", FieldRef("a"), FieldRef("b"))
    assert interp.eval(expr, ctx) is None


def test_rule_evaluation_pass():
    interp = ASTInterpreter(tolerance=0.01)
    rule = RuleNode(
        rule_id="test_subtotal_tax",
        description="Subtotal + Tax == Total",
        severity="error",
        condition=BinaryOp(
            "==", BinaryOp("+", FieldRef("subtotal"), FieldRef("tax")), FieldRef("total")
        ),
        message_template="Mismatch",
    )
    ctx = {"subtotal": 100.0, "tax": 10.0, "total": 110.0}
    passed, msg = interp.evaluate_rule(rule, ctx)
    assert passed is True
    assert msg is None


def test_rule_evaluation_fail():
    interp = ASTInterpreter(tolerance=0.01)
    rule = RuleNode(
        rule_id="test_subtotal_tax",
        description="Subtotal + Tax == Total",
        severity="error",
        condition=BinaryOp(
            "==", BinaryOp("+", FieldRef("subtotal"), FieldRef("tax")), FieldRef("total")
        ),
        message_template="Subtotal {subtotal} + Tax {tax} != Total {total}",
    )
    ctx = {"subtotal": 100.0, "tax": 10.0, "total": 150.0}
    passed, msg = interp.evaluate_rule(rule, ctx)
    assert passed is False
    assert "150.0" in msg


def test_declarative_rules_engine_end_to_end():
    engine = DeclarativeRulesEngine()

    # Valid invoice
    valid_inv = {"subtotal": 100.0, "tax": 8.0, "total": 108.0, "lines_sum": 100.0}
    findings = engine.evaluate(valid_inv)
    assert len(findings) == 0

    # Invalid arithmetic
    invalid_inv = {"subtotal": 100.0, "tax": 8.0, "total": 200.0, "lines_sum": 100.0}
    findings = engine.evaluate(invalid_inv)
    assert any(f["rule"] == "subtotal_plus_tax" for f in findings)


def test_engine_accepts_an_extracted_invoice(make_pdf):
    # Regression: evaluate() read `invoice.data`, an attribute ExtractedInvoice
    # never had, so passing the real extraction object raised AttributeError.
    from ledgerlens.extraction.extract import extract_pdf

    path, _ = make_pdf(41, error="crazy_tax")
    findings = DeclarativeRulesEngine().evaluate(extract_pdf(path))
    assert [(f["rule"], f["severity"]) for f in findings] == [("tax_rate_implausible", "error")]
    assert "%" in findings[0]["message"]


def test_dsl_and_imperative_rules_agree_on_the_corpus_errors(make_pdf):
    from ledgerlens.extraction.extract import extract_pdf
    from ledgerlens.validation.rules import validate_invoice

    engine = DeclarativeRulesEngine()
    shared = {"lines_vs_subtotal", "subtotal_plus_tax", "tax_rate_implausible"}
    for seed, error in [(51, "bad_total"), (52, "bad_subtotal"), (53, "crazy_tax"), (54, None)]:
        inv = extract_pdf(make_pdf(seed, error)[0])
        declarative = {f["rule"] for f in engine.evaluate(inv)}
        imperative = {f.rule for f in validate_invoice(inv)} & shared
        assert declarative == imperative, (seed, error)
