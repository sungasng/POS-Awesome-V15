"""
Phase 5 / P1 — Clone the verified "POS - Pedro (Test)" POS Profile to every
other outlet so all 21 branches can log in and make sales.

Source of truth (per Phase-5 handoff):
    - 1 working test profile already exists: "POS - Pedro (Test)" -> Pedro - SCL
    - 20 other outlets still need their own POS Profile
    - Same Customer Group (Retail), Currency (NGN), Price List (SCL Standard
      Selling), Payment Methods (Cash default + Bank Draft), Write-Off and
      Change-Amount accounts.
    - Territory per outlet is derived from the warehouse_name (matches the
      lpg_pricing.get_pos_profile_territory contract).
    - Applicable Users: any User whose email matches the outlet token
      (warehouse_name lower-cased; e.g., 'Ikeja' -> users with '@<warehouse>')
      OR an explicit OUTLET_CASHIER_MAP below.

Idempotent: if a profile for the outlet already exists it is UPDATED
(payments/users refreshed) rather than re-created. The verified test profile
"POS - Pedro (Test)" is left untouched.

Run on bench:
    bench --site sungasmis.v.frappe.cloud execute \
        "exec(open('/tmp/clone_pos_profiles_to_outlets.py').read())"

CUSTOMISATION: edit OUTLET_CASHIER_MAP below to assign specific cashiers
to specific outlets BEFORE running on production.
"""

from __future__ import annotations

import sys
from typing import Optional

import frappe


# -----------------------------------------------------------------------------
# CONFIG
# -----------------------------------------------------------------------------
COMPANY = "SUNGAS COMPANY LIMITED"
PRICE_LIST = "SCL Standard Selling"
CURRENCY = "NGN"
CUSTOMER_GROUP = "Retail"

# Always keep this profile alone (it's the manually-verified one).
PROTECTED_PROFILES = {"POS - Pedro (Test)"}

PAYMENTS = (
    # (mode_of_payment, default, amount)
    ("Cash", 1, 0),
    ("Bank Draft", 0, 0),
)

# Skip these warehouses (root/group/transit/special). Anything else that
# is a leaf warehouse under COMPANY gets a POS Profile.
SKIP_WAREHOUSE_TOKENS = (
    "transit",
    "in transit",
    "all warehouses",
    "rejected",
    "stores",  # generic 'Stores - <abbr>' default warehouse, not an outlet
    "work in progress",
    "finished goods",
)

# Optional: explicit override mapping {warehouse_name: [user_emails]}.
# If a warehouse is here, only those users are applicable for the profile.
# If absent, falls back to USERS_AUTODISCOVERY (see _resolve_cashiers).
OUTLET_CASHIER_MAP: dict[str, list[str]] = {
    # Example:
    # "Ikeja": ["cashier1@sungas.org", "cashier2@sungas.org"],
}

# When OUTLET_CASHIER_MAP doesn't have an entry, attempt to match users by:
#   user.email contains <warehouse_token>  OR
#   user.username contains <warehouse_token>  OR
#   user.full_name contains <warehouse_token>
# Always include Administrator.
USERS_AUTODISCOVERY = True


# -----------------------------------------------------------------------------
# HELPERS (reused from create_pos_profile_test.py)
# -----------------------------------------------------------------------------
def _pick_cost_center() -> str:
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


def _pick_account_by(preferences: list[dict]) -> Optional[str]:
    for filters in preferences:
        base = {"company": COMPANY, "is_group": 0, "disabled": 0}
        base.update(filters)
        rows = frappe.get_all(
            "Account", filters=base, pluck="name", order_by="name", limit=1
        )
        if rows:
            return rows[0]
    return None


def _pick_cash_account() -> str:
    abbr = frappe.db.get_value("Company", COMPANY, "abbr") or "SCL"
    rows = frappe.get_all(
        "Account",
        filters={"company": COMPANY, "is_group": 0, "account_type": "Cash"},
        pluck="name",
        order_by="name",
        limit=1,
    )
    if rows:
        return rows[0]
    rows = frappe.get_all(
        "Account",
        filters={"company": COMPANY, "is_group": 0, "name": ["like", "%Cash%"]},
        pluck="name",
        order_by="name",
        limit=1,
    )
    if rows:
        return rows[0]
    raise RuntimeError(
        f"No Cash account found on {COMPANY}. Create one (e.g. 'Cash - {abbr}') first."
    )


def _pick_writeoff_account(cash_account: str) -> str:
    val = frappe.db.get_value("Company", COMPANY, "write_off_account")
    if val:
        return val
    val = _pick_account_by([{"account_type": "Round Off"}])
    if val:
        return val
    val = _pick_account_by([
        {"name": ["like", "%Write Off%"]},
        {"account_name": ["like", "%Write Off%"]},
        {"name": ["like", "%Discount Allowed%"]},
        {"account_name": ["like", "%Discount Allowed%"]},
    ])
    if val:
        return val
    val = _pick_account_by([{"root_type": "Expense"}])
    if val:
        return val
    return cash_account


def _pick_change_amount_account(cash_account: str) -> str:
    val = frappe.db.get_value("Company", COMPANY, "default_cash_account")
    return val or cash_account


def _ensure_mop_default_account(mop_name: str, default_cash_account: str):
    mop = frappe.get_doc("Mode of Payment", mop_name)
    existing = next((a for a in (mop.accounts or []) if a.company == COMPANY), None)
    if existing:
        if not existing.default_account:
            existing.default_account = default_cash_account
            mop.save(ignore_permissions=True)
        return
    mop.append("accounts", {"company": COMPANY, "default_account": default_cash_account})
    mop.save(ignore_permissions=True)


# -----------------------------------------------------------------------------
# OUTLET ENUMERATION
# -----------------------------------------------------------------------------
def _list_outlet_warehouses() -> list[dict]:
    """
    Return every leaf warehouse under COMPANY that looks like an outlet.
    A warehouse is considered an outlet when:
      - is_group = 0
      - disabled = 0
      - warehouse_name does not match any SKIP_WAREHOUSE_TOKENS
      - a Territory exists with the same name as the warehouse_name
        (the lpg_pricing tier engine relies on this contract).
    """
    rows = frappe.get_all(
        "Warehouse",
        filters={"company": COMPANY, "is_group": 0, "disabled": 0},
        fields=["name", "warehouse_name"],
        order_by="warehouse_name",
    )
    outlets = []
    for row in rows:
        wname = (row.get("warehouse_name") or "").strip()
        if not wname:
            continue
        wlow = wname.lower()
        if any(token in wlow for token in SKIP_WAREHOUSE_TOKENS):
            continue
        # Require a matching Territory so tier pricing works out of the box.
        if not frappe.db.exists("Territory", wname):
            print(f"  SKIP {row['name']}: no Territory named {wname!r} (tier lookup would fail).")
            continue
        outlets.append({
            "warehouse": row["name"],
            "warehouse_name": wname,
        })
    return outlets


# -----------------------------------------------------------------------------
# CASHIER RESOLUTION
# -----------------------------------------------------------------------------
def _resolve_cashiers(warehouse_name: str) -> list[str]:
    explicit = OUTLET_CASHIER_MAP.get(warehouse_name)
    if explicit:
        return ["Administrator"] + [u for u in explicit if frappe.db.exists("User", u)]
    if not USERS_AUTODISCOVERY:
        return ["Administrator"]
    token = warehouse_name.lower().replace(" ", "")
    users = frappe.get_all(
        "User",
        filters={
            "enabled": 1,
        },
        or_filters={
            "email": ["like", f"%{token}%"],
            "username": ["like", f"%{token}%"],
            "full_name": ["like", f"%{warehouse_name}%"],
        },
        pluck="name",
        order_by="email",
    )
    return ["Administrator"] + [u for u in users if u != "Administrator"]


# -----------------------------------------------------------------------------
# UPSERT
# -----------------------------------------------------------------------------
def _upsert_profile(outlet: dict, cost_center: str, cash_account: str,
                    writeoff_account: str, change_amount_account: str,
                    income_account: str) -> tuple[str, str]:
    """
    Returns (profile_name, action) where action ∈ {"CREATED", "UPDATED", "SKIPPED"}.
    """
    wname = outlet["warehouse_name"]
    profile_name = f"POS - {wname}"

    if profile_name in PROTECTED_PROFILES:
        return profile_name, "SKIPPED-protected"

    users = _resolve_cashiers(wname)
    payment_rows = [
        {"mode_of_payment": mop, "default": is_default, "amount": amount}
        for mop, is_default, amount in PAYMENTS
    ]

    base_doc = {
        "doctype": "POS Profile",
        "name": profile_name,
        "company": COMPANY,
        "warehouse": outlet["warehouse"],
        "cost_center": cost_center,
        "currency": CURRENCY,
        "selling_price_list": PRICE_LIST,
        "customer_group": CUSTOMER_GROUP,
        "territory": wname,
        "write_off_account": writeoff_account,
        "write_off_cost_center": cost_center,
        "account_for_change_amount": change_amount_account,
        "income_account": income_account,
        "disabled": 0,
    }

    if frappe.db.exists("POS Profile", profile_name):
        prof = frappe.get_doc("POS Profile", profile_name)
        for k, v in base_doc.items():
            if k in ("doctype", "name"):
                continue
            setattr(prof, k, v)
        prof.applicable_for_users = []
        for u in users:
            prof.append("applicable_for_users", {"user": u})
        prof.payments = []
        for row in payment_rows:
            prof.append("payments", row)
        prof.save(ignore_permissions=True)
        return profile_name, "UPDATED"

    doc = frappe.get_doc({
        **base_doc,
        "applicable_for_users": [{"user": u} for u in users],
        "payments": payment_rows,
    })
    doc.insert(ignore_permissions=True)
    return profile_name, "CREATED"


# -----------------------------------------------------------------------------
# MAIN
# -----------------------------------------------------------------------------
def main():
    print("=" * 72)
    print(" Clone POS Profile to ALL outlets")
    print("=" * 72)

    # Prereqs
    if not frappe.db.exists("Company", COMPANY):
        print(f"  ERROR: Company {COMPANY!r} missing.")
        sys.exit(1)
    if not frappe.db.exists("Price List", PRICE_LIST):
        print(f"  ERROR: Price List {PRICE_LIST!r} missing.")
        sys.exit(1)
    if not frappe.db.exists("Customer Group", CUSTOMER_GROUP):
        print(f"  ERROR: Customer Group {CUSTOMER_GROUP!r} missing.")
        sys.exit(1)
    for mop, _, _ in PAYMENTS:
        if not frappe.db.exists("Mode of Payment", mop):
            print(f"  ERROR: Mode of Payment {mop!r} missing.")
            sys.exit(1)

    cost_center = _pick_cost_center()
    cash_account = _pick_cash_account()
    writeoff_account = _pick_writeoff_account(cash_account)
    change_amount_account = _pick_change_amount_account(cash_account)
    income_account = frappe.db.get_value("Company", COMPANY, "default_income_account")
    print(f"  cost_center           : {cost_center}")
    print(f"  cash account          : {cash_account}")
    print(f"  write-off account     : {writeoff_account}")
    print(f"  change-amount account : {change_amount_account}")
    print(f"  income account        : {income_account}")
    print()

    # Patch MoP default_account once globally (idempotent).
    for mop, _, _ in PAYMENTS:
        _ensure_mop_default_account(mop, cash_account)

    outlets = _list_outlet_warehouses()
    if not outlets:
        print("  No outlet warehouses found. Nothing to do.")
        sys.exit(0)

    print(f"  Found {len(outlets)} candidate outlet warehouses.")
    print()

    summary = {"CREATED": 0, "UPDATED": 0, "SKIPPED-protected": 0, "ERRORED": 0}
    errors: list[tuple[str, str]] = []

    for outlet in outlets:
        try:
            profile_name, action = _upsert_profile(
                outlet,
                cost_center=cost_center,
                cash_account=cash_account,
                writeoff_account=writeoff_account,
                change_amount_account=change_amount_account,
                income_account=income_account,
            )
            summary[action] = summary.get(action, 0) + 1
            users = _resolve_cashiers(outlet["warehouse_name"])
            print(f"  [{action:<18}] {profile_name:<35} -> "
                  f"{outlet['warehouse']:<25} users={len(users)}")
        except Exception as exc:  # noqa: BLE001
            summary["ERRORED"] += 1
            errors.append((outlet["warehouse_name"], str(exc)))
            print(f"  [ERROR             ] {outlet['warehouse_name']:<35} {exc}")

    frappe.db.commit()
    frappe.clear_cache()

    print()
    print("-" * 72)
    print(" Summary:")
    for k, v in summary.items():
        print(f"   {k:<20} {v}")
    if errors:
        print()
        print(" Errors (review and re-run if needed):")
        for w, e in errors:
            print(f"   - {w}: {e}")
    print("=" * 72)
    sys.exit(0 if not errors else 2)


# bench execute eval-scope fix (same trick as other Phase-5 scripts).
try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
