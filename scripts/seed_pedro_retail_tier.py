"""
Seed an LPG Outlet Price Tier for (Pedro outlet, Retail customer group) at
\u20a63,000/Kg. Required so the POS Awesome cart can resolve a tier rate
when a cashier at Pedro serves any Retail customer.

Idempotent: re-running updates the existing tier in place.

Run on bench:
    bench --site sungasmis.v.frappe.cloud execute \\
        "exec(open('/tmp/seed_pedro_retail_tier.py').read())"
"""

from __future__ import annotations

import sys

import frappe


ITEMS = ("LPG", "LPG-REFILL")
CUSTOMER_GROUP = "Retail"
TERRITORY = "Pedro"
RATE = 3000.0
CURRENCY = "NGN"


def _seed_one(item_code: str):
    if not frappe.db.exists("Item", item_code):
        print(f"  SKIP {item_code}: Item not found")
        return
    existing = frappe.db.get_value(
        "LPG Outlet Price Tier",
        {
            "item_code": item_code,
            "customer_group": CUSTOMER_GROUP,
            "territory": TERRITORY,
            "min_qty": 0,
        },
        "name",
    )
    if existing:
        tier = frappe.get_doc("LPG Outlet Price Tier", existing)
        before = tier.rate
        tier.rate = RATE
        tier.enabled = 1
        tier.notes = (tier.notes or "") + f"\n[seed] {before} -> {RATE}"
        tier.save(ignore_permissions=True)
        print(f"  UPDATED tier {existing} ({item_code}): rate {before} -> {RATE}")
    else:
        tier = frappe.get_doc({
            "doctype": "LPG Outlet Price Tier",
            "item_code": item_code,
            "customer_group": CUSTOMER_GROUP,
            "territory": TERRITORY,
            "min_qty": 0,
            "max_qty": 0,
            "rate": RATE,
            "currency": CURRENCY,
            "enabled": 1,
            "notes": "Seeded by seed_pedro_retail_tier.py",
        }).insert(ignore_permissions=True)
        print(f"  CREATED tier {tier.name} ({item_code}): \u20a6{RATE:,.0f}/Kg")


def main():
    print("=" * 70)
    print(f" Seed Pedro+Retail LPG tier(s) @ \u20a6{RATE:,.0f}/Kg")
    print("=" * 70)

    for dt, n in (("Customer Group", CUSTOMER_GROUP), ("Territory", TERRITORY)):
        if not frappe.db.exists(dt, n):
            print(f"  ERROR: {dt} {n!r} not found.")
            sys.exit(1)

    for item_code in ITEMS:
        _seed_one(item_code)

    frappe.db.commit()
    frappe.clear_cache()

    print()
    print("  Next:")
    print("    1. Hard-refresh POS Awesome (Ctrl+Shift+R), or open it in")
    print("       an Incognito / Private window.")
    print("    2. Open DevTools (F12) -> Console tab.")
    print("    3. Pick customer 'Cosmic' -> expect the [LPG-Tier] console logs")
    print("       AND the cart row's Rate column to change from 1,360 to 3,000.")
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
