"""
Create ONE test POS Profile to unblock POS Awesome login.

Profile created:
    Name              : POS - Pedro (Test)
    Company           : SUNGAS COMPANY LIMITED
    Warehouse         : Pedro - SCL
    Currency          : NGN
    Selling Price List: SCL Standard Selling
    Cost Center       : first leaf Sales-and-Marketing cost center
                        belonging to SCL (falls back to first SCL leaf cost
                        center if no Sales-and-Marketing match exists)
    Customer Group    : Retail            (filter — only Retail customers in POS)
    Territory         : Pedro
    Mode of Payment   : Cash (default), Bank Draft
    Applicable Users  : Administrator + 4 Pedro/test cashiers
                        (bolajoko.abilawon, bolanle.ayodele if they exist;
                         skip silently if not yet created)

Idempotent: if a profile with the same name exists, the script updates
its Applicable Users / Payment Methods rather than erroring.

Run on bench:
    bench --site sungasmis.v.frappe.cloud execute \\
        "exec(open('/tmp/create_pos_profile_test.py').read())"
"""

from __future__ import annotations

import sys

import frappe


PROFILE_NAME = "POS - Pedro (Test)"
COMPANY = "SUNGAS COMPANY LIMITED"
WAREHOUSE = "Pedro - SCL"
PRICE_LIST = "SCL Standard Selling"
CURRENCY = "NGN"
CUSTOMER_GROUP = "Retail"
TERRITORY = "Pedro"

CANDIDATE_USERS = (
    "Administrator",
    "bolajoko.abilawon@sungas.org",
    "bolanle.ayodele@sungas.org",
)

PAYMENTS = (
    # (mode_of_payment, default, amount)
    ("Cash", 1, 0),
    ("Bank Draft", 0, 0),
)


def _pick_cost_center() -> str:
    """Pick the most sensible default cost center.

    Preference order:
        1. Any leaf cost center with `Sales and Marketing` in the name (any outlet prefix)
        2. Any leaf cost center belonging to SCL
        3. The COMPANY-level main cost center
    """
    rows = frappe.get_all(
        "Cost Center",
        filters={
            "company": COMPANY,
            "is_group": 0,
            "cost_center_name": ["like", "%Sales and Marketing%"],
        },
        pluck="name",
        order_by="name",
        limit=1,
    )
    if rows:
        return rows[0]

    rows = frappe.get_all(
        "Cost Center",
        filters={"company": COMPANY, "is_group": 0},
        pluck="name",
        order_by="name",
        limit=1,
    )
    if rows:
        return rows[0]

    main = frappe.db.get_value("Company", COMPANY, "cost_center")
    if main:
        return main

    raise RuntimeError(f"No cost center found for company {COMPANY}.")


def _verify_prereqs():
    missing = []
    if not frappe.db.exists("Company", COMPANY):
        missing.append(f"Company {COMPANY!r}")
    if not frappe.db.exists("Warehouse", WAREHOUSE):
        missing.append(f"Warehouse {WAREHOUSE!r}")
    if not frappe.db.exists("Price List", PRICE_LIST):
        missing.append(f"Price List {PRICE_LIST!r}")
    if not frappe.db.exists("Customer Group", CUSTOMER_GROUP):
        missing.append(f"Customer Group {CUSTOMER_GROUP!r}")
    if not frappe.db.exists("Territory", TERRITORY):
        missing.append(f"Territory {TERRITORY!r}")
    for mop, _, _ in PAYMENTS:
        if not frappe.db.exists("Mode of Payment", mop):
            missing.append(f"Mode of Payment {mop!r}")
    if missing:
        print("  ERROR — prerequisites missing:")
        for m in missing:
            print(f"      - {m}")
        sys.exit(1)


def _existing_users() -> list[str]:
    users = []
    for u in CANDIDATE_USERS:
        if frappe.db.exists("User", u):
            users.append(u)
        else:
            print(f"  WARN: user {u!r} not found — skipping (run create_missing_cashiers.py)")
    return users


def _pick_cash_account() -> str:
    """Find a sensible default Cash account on SCL's chart of accounts."""
    # Preference order: account_type=Cash, then anything named 'Cash - <abbr>'.
    abbr = frappe.db.get_value("Company", COMPANY, "abbr") or "SCL"
    rows = frappe.get_all(
        "Account",
        filters={
            "company": COMPANY,
            "is_group": 0,
            "account_type": "Cash",
        },
        pluck="name",
        order_by="name",
        limit=1,
    )
    if rows:
        return rows[0]
    # fallback: any leaf account named like 'Cash - <abbr>' or 'Cash'
    rows = frappe.get_all(
        "Account",
        filters={
            "company": COMPANY,
            "is_group": 0,
            "name": ["like", "%Cash%"],
        },
        pluck="name",
        order_by="name",
        limit=1,
    )
    if rows:
        return rows[0]
    raise RuntimeError(
        f"No Cash account found on {COMPANY}. "
        f"Create one (e.g. 'Cash - {abbr}') before re-running."
    )


def _ensure_mop_default_account(mop_name: str, default_cash_account: str):
    """
    Make sure the Mode of Payment has a `default account` row for `COMPANY`.
    ERPNext POS Profile validation rejects any MoP that doesn't have one.
    """
    mop = frappe.get_doc("Mode of Payment", mop_name)
    existing = next(
        (a for a in (mop.accounts or []) if a.company == COMPANY),
        None,
    )
    if existing:
        if not existing.default_account:
            existing.default_account = default_cash_account
            mop.save(ignore_permissions=True)
            print(f"  PATCHED {mop_name}: default_account -> {default_cash_account}")
        return
    mop.append("accounts", {
        "company": COMPANY,
        "default_account": default_cash_account,
    })
    mop.save(ignore_permissions=True)
    print(f"  PATCHED {mop_name}: added default_account row for {COMPANY} -> {default_cash_account}")


def main():
    print("=" * 70)
    print(f" Create POS Profile: {PROFILE_NAME}")
    print("=" * 70)

    _verify_prereqs()
    cost_center = _pick_cost_center()
    print(f"  Using cost center: {cost_center}")

    cash_account = _pick_cash_account()
    print(f"  Using default cash account: {cash_account}")

    # Ensure each Mode of Payment used in this profile has a default account
    # for SCL — otherwise POS Profile.validate() rejects the profile.
    for mop, _, _ in PAYMENTS:
        _ensure_mop_default_account(mop, cash_account)

    users = _existing_users()
    print(f"  Applicable users ({len(users)}): {', '.join(users)}")

    payment_rows = [
        {"mode_of_payment": mop, "default": is_default, "amount": amount}
        for mop, is_default, amount in PAYMENTS
    ]

    if frappe.db.exists("POS Profile", PROFILE_NAME):
        prof = frappe.get_doc("POS Profile", PROFILE_NAME)
        prof.applicable_for_users = []
        for u in users:
            prof.append("applicable_for_users", {"user": u})
        prof.payments = []
        for row in payment_rows:
            prof.append("payments", row)
        prof.company = COMPANY
        prof.warehouse = WAREHOUSE
        prof.cost_center = cost_center
        prof.selling_price_list = PRICE_LIST
        prof.currency = CURRENCY
        prof.customer_group = CUSTOMER_GROUP
        prof.territory = TERRITORY
        prof.disabled = 0
        prof.save(ignore_permissions=True)
        action = "UPDATED"
    else:
        prof = frappe.get_doc({
            "doctype": "POS Profile",
            "name": PROFILE_NAME,
            "company": COMPANY,
            "warehouse": WAREHOUSE,
            "cost_center": cost_center,
            "currency": CURRENCY,
            "selling_price_list": PRICE_LIST,
            "customer_group": CUSTOMER_GROUP,
            "territory": TERRITORY,
            "write_off_account": frappe.db.get_value("Company", COMPANY, "write_off_account"),
            "write_off_cost_center": cost_center,
            "disabled": 0,
            "applicable_for_users": [{"user": u} for u in users],
            "payments": payment_rows,
        })
        prof.insert(ignore_permissions=True)
        action = "CREATED"

    frappe.db.commit()
    frappe.clear_cache()

    print()
    print(f"  {action} POS Profile {prof.name!r}")
    print(f"    company       : {prof.company}")
    print(f"    warehouse     : {prof.warehouse}")
    print(f"    cost_center   : {prof.cost_center}")
    print(f"    price_list    : {prof.selling_price_list}")
    print(f"    currency      : {prof.currency}")
    print(f"    customer_grp  : {prof.customer_group}")
    print(f"    territory     : {prof.territory}")
    print(f"    users         : {[u.user for u in prof.applicable_for_users]}")
    print(f"    payments      : {[p.mode_of_payment for p in prof.payments]}")

    print()
    print("  Next:")
    print("    1. Hard-refresh your browser  (Ctrl+Shift+R)")
    print("    2. Login as Administrator OR a Pedro cashier")
    print("    3. Open https://sungasmis.v.frappe.cloud/app/posapp")
    print(f"    4. Pick Company={COMPANY!r} and POS Profile={PROFILE_NAME!r}")
    print("    5. Enter Cash opening balance (e.g. 0) and click Submit.")
    print("=" * 70)
    sys.exit(0)


# bench execute eval-scope fix (same trick as other Phase-5 scripts).
try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
