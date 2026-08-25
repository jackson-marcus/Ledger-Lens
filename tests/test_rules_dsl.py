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
