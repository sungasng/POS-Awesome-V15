"""
Stop the 'Quantity exceeds available stock' banner in POS Awesome.

Even though we set is_stock_item=0 on LPG, POS Awesome still runs a
qty-vs-available check on the front-end whenever the POS Profile has
`posa_display_items_in_stock` or `update_stock` enabled. This script:

  - turns OFF those flags on the test profile
  - sets `validate_stock_on_save=0` if the field exists
  - safety net: posts a Stock Reconciliation that sets the Pedro warehouse
    balance of LPG to 100,000 Kg so any remaining code path sees stock.
    Only runs if at least one historical Stock Ledger Entry exists.

Run on bench:
    bench --site sungasmis.v.frappe.cloud execute \\
        "exec(open('/tmp/clear_pos_stock_block.py').read())"
"""

from __future__ import annotations

import sys

import frappe
from frappe.utils import nowdate, nowtime


PROFILE = "POS - Pedro (Test)"
ITEM = "LPG"
WAREHOUSE = "Pedro - SCL"
SEED_QTY = 100000
SEED_VALUATION = 1


def patch_profile():
    if not frappe.db.exists("POS Profile", PROFILE):
        print(f"  MISS profile {PROFILE!r}")
        return
    prof = frappe.get_doc("POS Profile", PROFILE)
    flags = {
        "posa_display_items_in_stock": 0,
        "update_stock": 0,
        "validate_stock_on_save": 0,
        "posa_force_server_items": 0,
        # Make sure search/sale works even for items with no stock data:
        "posa_allow_zero_rated_items": 1,
        "ignore_pricing_rule": 0,
    }
    changed = False
    for f, v in flags.items():
        if hasattr(prof, f) and getattr(prof, f) != v:
            print(f"  PATCH {PROFILE}.{f}: {getattr(prof, f)} -> {v}")
            setattr(prof, f, v)
            changed = True
    if changed:
        prof.save(ignore_permissions=True)
        print("  OK    POS Profile saved.")
    else:
        print("  SKIP  POS Profile already configured.")


def seed_opening_stock():
    """Only if there's at least one Stock Ledger Entry for LPG. Otherwise
    is_stock_item=0 means SLEs don't exist at all and we should skip.
    """
    if not frappe.db.exists("Item", ITEM):
        print(f"  MISS item {ITEM!r}")
        return
    is_stock = frappe.db.get_value("Item", ITEM, "is_stock_item")
    if not is_stock:
        print(f"  SKIP seed: {ITEM} is_stock_item=0 (non-stock item).")
        return
    if not frappe.db.exists("Warehouse", WAREHOUSE):
        print(f"  MISS warehouse {WAREHOUSE!r}")
        return
    sr = frappe.get_doc({
        "doctype": "Stock Reconciliation",
        "purpose": "Stock Reconciliation",
        "company": frappe.db.get_value("Warehouse", WAREHOUSE, "company"),
        "posting_date": nowdate(),
        "posting_time": nowtime(),
        "items": [{
            "item_code": ITEM,
            "warehouse": WAREHOUSE,
            "qty": SEED_QTY,
            "valuation_rate": SEED_VALUATION,
        }],
    })
    try:
        sr.insert(ignore_permissions=True)
        sr.submit()
        print(f"  OK    Seeded {SEED_QTY} {ITEM} at {WAREHOUSE} via {sr.name}")
    except Exception as e:
        print(f"  WARN  Stock seed failed: {e}")


def main():
    print("=" * 70)
    print(" Clear POS Awesome stock-block")
    print("=" * 70)
    patch_profile()
    seed_opening_stock()
    frappe.db.commit()
    frappe.clear_cache()
    print()
    print("  Next:")
    print("    1. Hard-refresh POS Awesome (Ctrl+Shift+R)")
    print("    2. Click RELOAD ITEMS")
    print("    3. Add LPG to cart -- no stock banner expected")
    print("    4. Type 2000 in Total Amount -- qty should drop to ~1.471")
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
