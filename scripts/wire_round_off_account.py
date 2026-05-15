"""
Sungas Phase-5: confirm Company.round_off_account is set on
SUNGAS COMPANY LIMITED so apply_cash_overage's rounding_adjustment
posts cleanly.

The user picked option (b) -- use the existing 'Round Off Expense - SCL'.
This script just verifies it's wired to the Company. Idempotent.

Run on bench:
    bench --site sungasmis.v.frappe.cloud execute \\
        "exec(open('/tmp/wire_round_off_account.py').read())"
"""

from __future__ import annotations

import sys

import frappe


COMPANY = "SUNGAS COMPANY LIMITED"
PREFERRED_ACCOUNTS = (
    "Round Off Expense - SCL",
    "Round Off - SCL",
)


def main():
    print("=" * 70)
    print(f" Verify Company.round_off_account on {COMPANY}")
    print("=" * 70)

    if not frappe.db.exists("Company", COMPANY):
        print(f"  ERROR: Company {COMPANY!r} not found.")
        sys.exit(1)

    current = frappe.db.get_value("Company", COMPANY, "round_off_account")
    print(f"  Current: {current!r}")

    if current and frappe.db.exists("Account", current):
        print(f"  OK: already set to {current!r}")
        sys.exit(0)

    # Find a usable account.
    pick = None
    for cand in PREFERRED_ACCOUNTS:
        if frappe.db.exists("Account", cand):
            pick = cand
            break
    if not pick:
        # Search for any account named 'Round Off'.
        rows = frappe.get_all(
            "Account",
            filters={"company": COMPANY, "name": ["like", "%Round Off%"]},
            pluck="name",
            limit=1,
        )
        if rows:
            pick = rows[0]
    if not pick:
        print(f"  ERROR: no 'Round Off' account found on {COMPANY}.")
        print("    Create one in /app/account and re-run.")
        sys.exit(1)

    frappe.db.set_value("Company", COMPANY, "round_off_account", pick)

    # Also set round_off_cost_center if missing.
    if not frappe.db.get_value("Company", COMPANY, "round_off_cost_center"):
        cc = frappe.get_all(
            "Cost Center",
            filters={
                "company": COMPANY,
                "is_group": 0,
                "cost_center_name": ["like", "%Sales and Marketing%"],
            },
            pluck="name",
            limit=1,
        )
        if cc:
            frappe.db.set_value("Company", COMPANY, "round_off_cost_center", cc[0])

    frappe.db.commit()
    frappe.clear_cache()
    print(f"  WIRED Company.round_off_account = {pick!r}")
    print("=" * 70)
    sys.exit(0)


try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
