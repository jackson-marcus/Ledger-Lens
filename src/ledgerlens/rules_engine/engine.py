"""Rules Engine DSL - Declarative Rules Engine.

Manages collections of AST rules, executes them against invoice contexts,
and emits structured findings.
"""

from __future__ import annotations

from typing import Any

from ledgerlens.extraction.extract import ExtractedInvoice
from ledgerlens.rules_engine.ast_nodes import (
    BinaryOp,
    ConditionNode,
    FieldRef,
    Literal,
    RuleNode,
)
from ledgerlens.rules_engine.interpreter import ASTInterpreter
from ledgerlens.settings import get_config


class DeclarativeRulesEngine:
    """Evaluates declarative AST rules against invoice extractions."""

    def __init__(self, tolerance: float | None = None) -> None:
        cfg = get_config()["validation"]
        tol = tolerance if tolerance is not None else cfg["amount_tolerance"]
        self.interpreter = ASTInterpreter(tolerance=tol)
        self.rules: list[RuleNode] = self._build_default_rules(cfg)

    def _build_default_rules(self, cfg: dict) -> list[RuleNode]:
        """Construct standard AST validation rules."""
        rules: list[RuleNode] = []

        # Rule 1: lines_sum == subtotal
        # condition: if lines_sum and subtotal present, abs_diff_lte(lines_sum, subtotal)
        rule_lines_subtotal = RuleNode(
            rule_id="lines_vs_subtotal",
            description="Line items sum must equal subtotal",
            severity="error",
            condition=ConditionNode(
                "implies",
                [
                    ConditionNode(
                        "and",
                        [
                            ConditionNode("is_not_null", [FieldRef("subtotal")]),
                            ConditionNode("is_not_null", [FieldRef("lines_sum")]),
                        ],
                    ),
                    BinaryOp("abs_diff_lte", FieldRef("lines_sum"), FieldRef("subtotal")),
                ],
            ),
            message_template="Line items sum to {lines_sum:.2f} but subtotal reads {subtotal:.2f}",
        )
        rules.append(rule_lines_subtotal)

        # Rule 2: subtotal + tax == total
        rule_subtotal_tax = RuleNode(
            rule_id="subtotal_plus_tax",
            description="Subtotal plus tax must equal total",
            severity="error",
            condition=ConditionNode(
                "implies",
                [
                    ConditionNode(
                        "and",
                        [
                            ConditionNode("is_not_null", [FieldRef("subtotal")]),
                            ConditionNode("is_not_null", [FieldRef("tax")]),
                            ConditionNode("is_not_null", [FieldRef("total")]),
                        ],
                    ),
                    BinaryOp(
                        "abs_diff_lte",
                        BinaryOp("+", FieldRef("subtotal"), FieldRef("tax")),
                        FieldRef("total"),
                    ),
                ],
            ),
            message_template="Subtotal {subtotal:.2f} + tax {tax:.2f} does not equal total {total:.2f}",
        )
        rules.append(rule_subtotal_tax)

        # Rule 3: tax_rate <= max_tax_rate
        rule_tax_rate = RuleNode(
            rule_id="tax_rate_implausible",
            description=f"Tax rate exceeds {cfg['max_tax_rate'] * 100:.0f}%",
            severity="error",
            condition=ConditionNode(
                "implies",
                [
                    ConditionNode(
                        "and",
                        [
                            ConditionNode("is_not_null", [FieldRef("subtotal")]),
                            ConditionNode("is_not_null", [FieldRef("tax")]),
                            BinaryOp(">", FieldRef("subtotal"), Literal(0.0)),
                        ],
                    ),
                    BinaryOp(
                        "<=",
                        BinaryOp("/", FieldRef("tax"), FieldRef("subtotal")),
                        Literal(cfg["max_tax_rate"]),
                    ),
                ],
            ),
            message_template="Tax rate ({tax_rate_pct:.1f}%) exceeds plausibility ceiling",
        )
        rules.append(rule_tax_rate)

        return rules

    def evaluate(self, invoice: ExtractedInvoice | dict[str, Any]) -> list[dict[str, Any]]:
        """Run all declarative rules against an invoice and return findings."""
        ctx = (
            dict(invoice)
            if isinstance(invoice, dict)
            else {name: fv.value for name, fv in invoice.fields.items()}
        )
        # Compute helper keys
        subtotal = ctx.get("subtotal")
        tax = ctx.get("tax")
        if isinstance(subtotal, int | float) and isinstance(tax, int | float) and subtotal > 0:
            ctx["tax_rate_pct"] = (tax / subtotal) * 100.0

        findings = []
        for rule in self.rules:
            passed, msg = self.interpreter.evaluate_rule(rule, ctx)
            if not passed:
                findings.append(
                    {
                        "rule": rule.rule_id,
                        "severity": rule.severity,
                        "message": msg or rule.description,
                    }
                )
        return findings
