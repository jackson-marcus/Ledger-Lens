# LedgerLens — Invoice AI & Audit (Declarative Rules Engine DSL)

<div align="center">

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Streamlit](https://img.shields.io/badge/Streamlit-App-FF4B4B.svg?logo=streamlit&logoColor=white)](https://streamlit.io/)
[![MLflow](https://img.shields.io/badge/MLflow-Registry-0194E2.svg?logo=mlflow&logoColor=white)](https://mlflow.org/)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED.svg?logo=docker&logoColor=white)](https://www.docker.com/)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Tests: Pytest](https://img.shields.io/badge/tests-pytest-blue.svg?logo=pytest&logoColor=white)](https://pytest.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

</div>

> **Financial document AI and automated invoice audit engine powered by a Declarative Domain-Specific Language (DSL) and Tree-Walking AST Interpreter — executing deterministic accounting rules, mathematical reconciliations, and expense policy RAG.**

---

## 🏛️ Architecture Pattern: Declarative Rules Engine DSL + AST Interpreter

Hardcoding accounting validation logic in python `if-else` blocks causes audit rule drift, lacks explanation transparency, and requires code deployments for routine policy updates.

`ledgerlens` compiles audit policies into an **Abstract Syntax Tree (AST)** evaluated by a pure tree-walking interpreter:

```mermaid
graph TD
    subgraph Input_Record ["Extracted Invoice Record"]
        Inv["{subtotal: 100.0, tax: 8.0, total: 108.0, lines_sum: 100.0}"]
    end

    subgraph AST_Rule_Hierarchy ["Declarative AST Expression Tree"]
        Rule["RuleNode: subtotal_plus_tax (severity='error')"]
        Implies["ConditionNode: implies"]
        NotNull["ConditionNode: and(is_not_null([subtotal, tax, total]))"]
        AbsDiff["BinaryOp: abs_diff_lte"]
        Add["BinaryOp: subtotal + tax"]
        TotRef["FieldRef: total"]

        Rule --> Implies
        Implies --> NotNull
        Implies --> AbsDiff
        AbsDiff --> Add
        AbsDiff --> TotRef
    end

    subgraph Interpreter_Engine ["Tree-Walking ASTInterpreter"]
        Eval["ASTInterpreter.evaluate_rule()<br/>• Null-safe evaluation<br/>• Floating-point tolerance bounds<br/>• Explanatory error formatting"]
    end

    subgraph Audit_Findings ["Structured Audit Findings"]
        F["list[Finding]<br/>[rule_id, severity, formatted_message]"]
    end

    Inv --> Eval
    AST_Rule_Hierarchy --> Eval
    Eval --> F
```

### AST Expression Grammar
- **`FieldRef`**: Resolves dynamic fields from invoice context with null safety.
- **`Literal`**: Constant scalar floats, integers, or strings.
- **`BinaryOp`**: Arithmetic operators (`+`, `-`, `*`, `/`) and comparisons (`==`, `<`, `<=`, `>`, `>=`, `abs_diff_lte`).
- **`ConditionNode`**: Boolean logic operators (`and`, `or`, `not`, `implies`, `is_not_null`).
- **`RuleNode`**: Combines AST conditions with error severity and message interpolation templates.

### Module Organization
- **`rules_engine/ast_nodes.py`**: Typed immutable AST node hierarchy.
- **`rules_engine/interpreter.py`**: Pure tree-walking `ASTInterpreter` with tolerance arithmetic.
- **`rules_engine/engine.py`**: `DeclarativeRulesEngine` managing rulesets and audit workflows.
- **`extraction/`**: Multimodal field extraction from digital/scanned PDFs.
- **`rag/`**: Expense policy retriever with exact line provenance citations.

---

## 🧾 Core Methodologies & Financial Validation

### 1. Mathematical Reconciliation Rules
- Subtotal Integrity: $|\sum (\text{Qty}_i \times \text{Price}_i) - \text{Subtotal}| \le \epsilon$
- Grand Total Integrity: $|(\text{Subtotal} + \text{Tax}) - \text{Grand Total}| \le \epsilon$
- Tax Rate Sanity: $\frac{\text{Tax}}{\text{Subtotal}} \le \text{MaxTaxRate}$

### 2. Expense Policy RAG with Line Citations
- Semantic search across corporate procurement and travel & expense guidelines.
- Grounded compliance verdicts citing verbatim clause references.

---

## 🚀 Quickstart & Setup Guide

```bash
git clone https://github.com/jackson-marcus/ledgerlens.git
cd ledgerlens

$env:UV_CACHE_DIR = "D:\ml-projects\.uv-cache"
uv sync --group dev

# Run unit tests and AST rule engine verification
uv run pytest -q
uv run ruff check .

# Launch FastAPI (port :8070) + Streamlit auditor (port :8571)
make api
make ui
```

---

## 📂 Repository Layout

```
ledgerlens/
├── configs/                      # Accounting tolerance & validation rules configs
├── data/                         # Sample invoice PDFs and synthetic benchmarks
├── src/ledgerlens/               # Core Python package
│   ├── rules_engine/             # Declarative Rules DSL: AST nodes, interpreter, engine
│   ├── validation/               # Validation adapter layer
│   ├── extraction/               # OCR and invoice field parsing
│   ├── rag/                      # Corporate expense policy retriever
│   ├── api/                      # FastAPI REST routes
│   └── ui/                       # Streamlit interactive invoice workspace
├── tests/                        # Comprehensive Pytest suite covering AST rules and RAG
├── docker-compose.yml
└── pyproject.toml
```

---

## 👤 Author & Contact

**Jackson Marcus**
- **Email:** [jackson.marcus.work@gmail.com](mailto:jackson.marcus.work@gmail.com)
- **Upwork:** [Jackson Marcus on Upwork](https://www.upwork.com/freelancers/~012235717501ad9c7b)
- **GitHub:** [@jackson-marcus](https://github.com/jackson-marcus)

---

## 👨‍💻 Author & Maintainer

<div align="center">

### **Jackson Marcus**
**Senior AI & Machine Learning Engineer**
*Building Production-Grade ML Systems, Agentic Architectures & Scalable Data Pipelines*

[![GitHub Profile](https://img.shields.io/badge/GitHub-jackson--marcus-181717?style=for-the-badge&logo=github&logoColor=white)](https://github.com/jackson-marcus)
[![Upwork Portfolio](https://img.shields.io/badge/Upwork-Top%20Rated%20Plus-14A800?style=for-the-badge&logo=upwork&logoColor=white)](https://www.upwork.com/freelancers/~012235717501ad9c7b)
[![Email Contact](https://img.shields.io/badge/Email-wajahatanees41%40gmail.com-D14836?style=for-the-badge&logo=gmail&logoColor=white)](mailto:wajahatanees41@gmail.com)

📍 *Byron, GA, USA*

</div>
