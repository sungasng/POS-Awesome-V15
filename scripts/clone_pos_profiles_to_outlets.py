"""
Phase 5.5 — Clone POS Profile to every Sungas outlet using OUTLET-SPECIFIC
cash/transfer/POS-incoming accounts AND cost centers AND region tagging.

Requires `phase55_setup.py` and `install_pos_print_format.py` to have been
run on the bench first (renames cost centers, creates missing accounts /
branches / region doctype, installs the 58mm Print Format).

Run on bench:
    curl -fsSL https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/develop/scripts/clone_pos_profiles_to_outlets.py \
      -o /tmp/clone_pos_profiles_to_outlets.py && \
    bench --site sungasmis.v.frappe.cloud execute \
      "exec(open('/tmp/clone_pos_profiles_to_outlets.py').read())"
"""

from __future__ import annotations

import sys
from typing import Optional

import frappe


COMPANY = "SUNGAS COMPANY LIMITED"
PRICE_LIST = "SCL Standard Selling"
CURRENCY = "NGN"
CUSTOMER_GROUP = "Retail"
DEFAULT_PRINT_FORMAT = "Sungas Thermal 58mm"

PROTECTED_PROFILES = {"POS - Pedro (Test)"}

PAYMENTS = (
    ("Cash", 1, 0),
    ("Bank Draft", 0, 0),
)

SKIP_WAREHOUSE_TOKENS = (
    "transit", "in transit", "all warehouses", "rejected",
    "stores", "work in progress", "finished goods",
)

OUTLET_CASHIER_MAP: dict[str, list[str]] = {
    # Fill before running on prod: { "Pedro": ["cashier@sungas.org", ...] }
}

USERS_AUTODISCOVERY = True

OUTLET_ACCT_ALIASES: dict[str, list[str]] = {
    "Ebutte": ["Ebutte", "Ebute"],
    "Iju-Otta": ["Iju-Otta", "Iju-Ota", "Iju Ota"],
    "Osi-Otta": ["Osi-Otta", "Osi-Ota", "Osi Ota"],
}

OUTLET_REGION: dict[str, str] = {
    "Maba": "Ogun 1", "Sefu": "Ogun 1", "Ebutte": "Ogun 1", "Aseese": "Ogun 1",
    "Itele": "Ogun 2", "Iju-Otta": "Ogun 2", "Osi-Otta": "Ogun 2", "Ijoko": "Ogun 2",
    "Ikeja": "Lagos 1", "Oworo": "Lagos 1", "Pedro": "Lagos 1",
    "Bolade": "Lagos 1", "Mafoluku": "Lagos 1",
    "Eleme": "Rivers 1", "Reclamation": "Rivers 1",
    "Ekehuan": "Edo 1", "Upper Mission": "Edo 1", "Idowina": "Edo 1",
    "Idokpa": "Edo 1", "Okhuoromi": "Edo 1",
    "Asaba": "Delta 1",
}


# ---------------------------------------------------------------- HELPERS
def _alias_tokens(outlet: str) -> list[str]:
    return OUTLET_ACCT_ALIASES.get(outlet, [outlet])


def _find_account(outlet: str, search: str) -> Optional[str]:
    for token in _alias_tokens(outlet):
        rows = frappe.get_all(
            "Account",
            filters={
                "company": COMPANY, "is_group": 0, "disabled": 0,
                "account_name": ["like", f"%{search}%"],
            },
            fields=["name", "account_name"],
        )
        for r in rows:
            n = r["account_name"].lower().replace("-", " ").replace("  ", " ")
            if token.lower().replace("-", " ") in n:
                return r["name"]
    return None


def _find_cost_center(outlet: str) -> Optional[str]:
    rows = frappe.get_all(
        "Cost Center",
        filters={
            "company": COMPANY, "is_group": 0,
            "cost_center_name": ["like", f"%Sales and Marketing {outlet}%"],
        },
        pluck="name",
        limit=1,
    )
    if rows:
        return rows[0]
    # Fallback: try any of the outlet aliases (Ebute / Iju-Ota / Osi-Ota).
    for alias in _alias_tokens(outlet):
        if alias == outlet:
            continue
        rows = frappe.get_all(
            "Cost Center",
            filters={
                "company": COMPANY, "is_group": 0,
                "cost_center_name": ["like", f"%Sales and Marketing {alias}%"],
            },
            pluck="name",
            limit=1,
        )
        if rows:
            return rows[0]
    return None


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


# ---------------------------------------------------------------- LIST OUTLETS
def _list_outlet_warehouses() -> list[dict]:
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
        if not frappe.db.exists("Territory", wname):
            print(f"  SKIP {row['name']}: no Territory named {wname!r} (tier lookup would fail).")
            continue
        outlets.append({
            "warehouse": row["name"],
            "warehouse_name": wname,
        })
    return outlets


# ---------------------------------------------------------------- CASHIERS
def _resolve_cashiers(warehouse_name: str) -> list[str]:
    explicit = OUTLET_CASHIER_MAP.get(warehouse_name)
    if explicit:
        return ["Administrator"] + [u for u in explicit if frappe.db.exists("User", u)]
    if not USERS_AUTODISCOVERY:
        return ["Administrator"]
    token = warehouse_name.lower().replace(" ", "").replace("-", "")
    users = frappe.get_all(
        "User",
        filters={"enabled": 1},
        or_filters={
            "email": ["like", f"%{token}%"],
            "username": ["like", f"%{token}%"],
            "full_name": ["like", f"%{warehouse_name}%"],
        },
        pluck="name",
        order_by="email",
    )
    return ["Administrator"] + [u for u in users if u != "Administrator"]


# ---------------------------------------------------------------- UPSERT
def _upsert_profile(outlet: dict) -> tuple[str, str, dict]:
    wname = outlet["warehouse_name"]
    profile_name = f"POS - {wname}"

    if profile_name in PROTECTED_PROFILES:
        return profile_name, "SKIPPED-protected", {}

    cash = _find_account(wname, "Cash Sales")
    transfer = _find_account(wname, "Incoming Transfer")
    pos_incoming = _find_account(wname, "POS Incoming")
    cost_center = _find_cost_center(wname)

    missing = []
    if not cash:
        missing.append("cash")
    if not transfer:
        missing.append("transfer")
    if not pos_incoming:
        missing.append("pos_incoming")
    if not cost_center:
        missing.append("cost_center")
    if missing:
        return profile_name, f"SKIPPED-missing:{','.join(missing)}", {
            "cash": cash, "transfer": transfer, "pos_incoming": pos_incoming,
            "cost_center": cost_center,
        }

    users = _resolve_cashiers(wname)

    # Three payment methods per outlet, each with its own per-outlet account.
    payment_rows = [
        {"mode_of_payment": "Cash", "default": 1, "amount": 0, "account": cash},
        {"mode_of_payment": "Bank Draft", "default": 0, "amount": 0, "account": transfer},
    ]
    if frappe.db.exists("Mode of Payment", "POS"):
        payment_rows.append({"mode_of_payment": "POS", "default": 0, "amount": 0,
                              "account": pos_incoming})

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
        "write_off_account": cost_center.split(" - ", 1)[0] if False else
            frappe.db.get_value("Company", COMPANY, "round_off_account"),
        "write_off_cost_center": cost_center,
        "account_for_change_amount": cash,
        "income_account": frappe.db.get_value("Company", COMPANY, "default_income_account"),
        "print_format": DEFAULT_PRINT_FORMAT
            if frappe.db.exists("Print Format", DEFAULT_PRINT_FORMAT) else None,
        "disabled": 0,
    }

    # Auto-fill MoP default_account so resumed sales still post correctly.
    _ensure_mop_default_account("Cash", cash)
    _ensure_mop_default_account("Bank Draft", transfer)
    if frappe.db.exists("Mode of Payment", "POS"):
        _ensure_mop_default_account("POS", pos_incoming)

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
        # Tag the Region accounting dimension if the doctype + dimension exist.
        region = OUTLET_REGION.get(wname)
        if region and hasattr(prof, "sungas_region"):
            prof.sungas_region = region
        prof.save(ignore_permissions=True)
        return profile_name, "UPDATED", base_doc

    doc = frappe.get_doc({
        **base_doc,
        "applicable_for_users": [{"user": u} for u in users],
        "payments": payment_rows,
    })
    region = OUTLET_REGION.get(wname)
    if region and hasattr(doc, "sungas_region"):
        doc.sungas_region = region
    doc.insert(ignore_permissions=True)
    return profile_name, "CREATED", base_doc


# ---------------------------------------------------------------- MAIN
def main():
    print("=" * 78)
    print(" Clone POS Profile to ALL outlets (Phase-5.5 multi-account version)")
    print("=" * 78)

    if not frappe.db.exists("Company", COMPANY):
        print(f"  ERROR: Company {COMPANY!r} missing.")
        sys.exit(1)
    if not frappe.db.exists("Print Format", DEFAULT_PRINT_FORMAT):
        print(f"  WARNING: Print Format {DEFAULT_PRINT_FORMAT!r} not installed.")
        print("           Run install_pos_print_format.py first to ship the 58mm thermal layout.")

    outlets = _list_outlet_warehouses()
    print(f"  Found {len(outlets)} outlet warehouses.")
    print()

    summary = {}
    errors = []
    for outlet in outlets:
        try:
            name, action, base = _upsert_profile(outlet)
            summary[action] = summary.get(action, 0) + 1
            print(f"  [{action:<32}] {name:<35}")
            if action.startswith(("CREATED", "UPDATED")):
                print(f"      cash         = {base.get('account_for_change_amount')}")
                print(f"      cost_center  = {base.get('cost_center')}")
                print(f"      print_format = {base.get('print_format')}")
        except Exception as exc:  # noqa: BLE001
            summary["ERRORED"] = summary.get("ERRORED", 0) + 1
            errors.append((outlet["warehouse_name"], str(exc)))
            print(f"  [ERROR] {outlet['warehouse_name']}: {exc}")

    frappe.db.commit()
    frappe.clear_cache()

    print("\n" + "-" * 78)
    print(" Summary:")
    for k, v in summary.items():
        print(f"   {k:<32} {v}")
    if errors:
        print("\n Errors:")
        for w, e in errors:
            print(f"   - {w}: {e}")
    print("=" * 78)
    sys.exit(0 if not errors else 2)


try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
