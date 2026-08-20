"""Generate the accounting-policy knowledge base (markdown docs).

Usage:
    python -m ledgerlens.rag.policies
"""

from __future__ import annotations

from ledgerlens.settings import get_config, resolve_path

POLICIES = {
    "expense-policy.md": """# Expense Policy

## Approval thresholds
Invoices up to 1,000 USD may be approved by a team lead. Between 1,000 and
10,000 USD requires a department head. Above 10,000 USD requires the finance
director and a purchase order reference.

## Payment terms
Standard supplier terms are net 30. Terms longer than 60 days require written
CFO approval; terms longer than 120 days are never acceptable.

## Duplicate handling
An invoice number may be paid exactly once per vendor. Suspected duplicates
are routed to the accounts-payable review queue and must not be paid until
cleared.
""",
    "tax-policy.md": """# Tax Policy

## Plausible tax rates
US state sales tax ranges roughly 0 to 11 percent. UK VAT is 20 percent.
German VAT is 19 percent. Canadian HST is 13 to 15 percent. Any invoice whose
implied tax rate exceeds 30 percent must be escalated to the tax team.

## Zero-rated purchases
Wholesale purchases for resale and certain safety equipment can legitimately
carry zero tax. A missing tax line is not automatically an error.
""",
    "vendor-policy.md": """# Vendor Policy

## Onboarding
New vendors require a W-9 (US) or local equivalent before first payment.
Payments to vendors not in the vendor master are blocked.

## Dispute process
Arithmetic discrepancies above 0.02 in an invoice are disputed in writing
within 10 business days, quoting the invoice number, the line items, and the
computed versus stated amounts. Goods are not returned before finance signs
off.
""",
    "capitalization-policy.md": """# Capitalization Policy

Equipment purchases above 2,500 USD with a useful life beyond one year are
capitalized as fixed assets, not expensed. Software licenses of one year or
less are expensed; multi-year licenses are amortized over the license term.
Maintenance and repair costs are always expensed.
""",
}


def main() -> None:
    out = resolve_path(get_config()["rag"]["policy_dir"])
    out.mkdir(parents=True, exist_ok=True)
    for name, text in POLICIES.items():
        (out / name).write_text(text, encoding="utf-8")
    print(f"Wrote {len(POLICIES)} policy docs -> {out}")


if __name__ == "__main__":
    main()
