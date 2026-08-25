"""Rules Engine DSL - Tree-Walking AST Interpreter.

Evaluates AST rule trees against an input dictionary or ExtractedInvoice object.
"""

from __future__ import annotations

import math
from typing import Any

from ledgerlens.rules_engine.ast_nodes import (
    ASTNode,
    BinaryOp,
    ConditionNode,
    FieldRef,
    Literal,
    RuleNode,
    UnaryOp,
)


class EvaluationError(Exception):
    """Raised on invalid AST operations during rule interpretation."""


class ASTInterpreter:
    """Tree-walking evaluator for rule expressions."""

    def __init__(self, tolerance: float = 0.02) -> None:
        self.tolerance = tolerance

    def eval(self, node: ASTNode, context: dict[str, Any]) -> Any:
        """Recursively evaluate an ASTNode in the provided record context."""
        if isinstance(node, Literal):
            return node.value

        if isinstance(node, FieldRef):
            val = context.get(node.name)
            if isinstance(val, int | float):
                return float(val)
            return val

        if isinstance(node, UnaryOp):
            val = self.eval(node.expr, context)
            if val is None:
                return None
            if node.op == "abs":
                return abs(val)
            if node.op == "not":
                return not bool(val)
            raise EvaluationError(f"Unsupported unary operator {node.op!r}")

        if isinstance(node, BinaryOp):
            left = self.eval(node.left, context)
            right = self.eval(node.right, context)
            if left is None or right is None:
                return None

            op = node.op
            if op == "+":
                return left + right
            if op == "-":
                return left - right
            if op == "*":
                return left * right
            if op == "/":
                return left / right if right != 0 else math.nan
            if op == "==":
                return (
                    abs(left - right) <= self.tolerance
                    if isinstance(left, float)
                    else left == right
                )
            if op == "!=":
                return (
                    abs(left - right) > self.tolerance if isinstance(left, float) else left != right
                )
            if op == "<":
                return left < right
            if op == "<=":
                return left <= right
            if op == ">":
                return left > right
            if op == ">=":
                return left >= right
            if op == "abs_diff_lte":
                return abs(left - right) <= self.tolerance
            raise EvaluationError(f"Unsupported binary operator {op!r}")

        if isinstance(node, ConditionNode):
            op = node.op
            if op == "is_not_null":
                val = self.eval(node.operands[0], context)
                return val is not None
            if op == "is_null":
                val = self.eval(node.operands[0], context)
                return val is None
            if op == "and":
                for operand in node.operands:
                    res = self.eval(operand, context)
                    if res is not True:
                        return False
                return True
            if op == "or":
                for operand in node.operands:
                    res = self.eval(operand, context)
                    if res is True:
                        return True
                return False
            if op == "implies":
                # A implies B  <=>  (not A) or B
                premise = self.eval(node.operands[0], context)
                if not premise:
                    return True
                return bool(self.eval(node.operands[1], context))
            raise EvaluationError(f"Unsupported condition operator {op!r}")

        raise EvaluationError(f"Unknown AST node type: {type(node)}")

    def evaluate_rule(self, rule: RuleNode, context: dict[str, Any]) -> tuple[bool, str | None]:
        """Evaluate a RuleNode. Returns (passed: bool, message: str | None)."""
        passed = self.eval(rule.condition, context)
        if passed is True or passed is None:
            return True, None

        # Format failure message from template
        try:
            msg = rule.message_template.format(**context)
        except Exception:
            msg = rule.description
        return False, msg
