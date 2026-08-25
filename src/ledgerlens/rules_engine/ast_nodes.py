"""Rules Engine DSL - Abstract Syntax Tree (AST) Nodes.

Typed AST hierarchy representing declarative business logic rules and mathematical expressions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ASTNode:
    """Base node in the rule expression AST."""


@dataclass(frozen=True)
class FieldRef(ASTNode):
    """Reference to a field in the input record (e.g. 'subtotal', 'total')."""

    name: str


@dataclass(frozen=True)
class Literal(ASTNode):
    """Constant scalar value."""

    value: Any


@dataclass(frozen=True)
class BinaryOp(ASTNode):
    """Binary operation: left OP right (e.g. '+', '-', '*', '/', '==', '!=', '<', '<=', '>', '>=', 'abs_diff_lte')."""

    op: str
    left: ASTNode
    right: ASTNode


@dataclass(frozen=True)
class UnaryOp(ASTNode):
    """Unary operation: OP expr (e.g. 'not', 'abs')."""

    op: str
    expr: ASTNode


@dataclass(frozen=True)
class ConditionNode(ASTNode):
    """Logical condition evaluating to boolean (e.g. AND, OR, NOT, comparisons)."""

    op: str  # 'and', 'or', 'not', 'is_not_null', 'is_null'
    operands: list[ASTNode]


@dataclass(frozen=True)
class RuleNode:
    """A declared business rule with condition, severity, and failure message template."""

    rule_id: str
    description: str
    severity: str  # 'error' | 'warning'
    condition: ASTNode  # must evaluate to True for the rule to PASS (violation if False)
    message_template: str
