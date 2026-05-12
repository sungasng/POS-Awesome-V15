"""
Disable inventory tracking on a list of items so POS Awesome can sell them
without an opening-stock entry. Useful for "gas-by-the-kg" or service-style
items where the cashier collects cash, but stock isn't physically tracked
in ERPNext.

Default item list: ITEMS_TO_DISABLE (edit below).

Run on bench:
    bench --site sungasmis.v.frappe.cloud execute \\
        "exec(open('/tmp/disable_item_stock.py').read())"

Effect per item:
    is_stock_item     = 0    (turns off inventory tracking)
    has_batch_no      = 0    (no longer needed)
    has_serial_no     = 0
    include_item_in_manufacturing = 0

Idempotent: items already non-stock are skipped.
"""

from __future__ import annotations

import sys

import frappe


ITEMS_TO_DISABLE = (
    "LPG",
)


def main():
    print("=" * 70)
    print(" Disable stock tracking on POS items")
    print("=" * 70)
    changed = 0
    skipped = 0
    missing = []

    for item_code in ITEMS_TO_DISABLE:
        if not frappe.db.exists("Item", item_code):
            print(f"  MISS  {item_code}  (Item not found)")
            missing.append(item_code)
            continue

        item = frappe.get_doc("Item", item_code)
        if item.is_stock_item == 0:
            print(f"  SKIP  {item_code}  (already non-stock)")
            skipped += 1
            continue

        # Detect blockers: open Stock Ledger Entries / Bin balances.
        sl_count = frappe.db.count("Stock Ledger Entry",
                                    {"item_code": item_code, "is_cancelled": 0})
        if sl_count:
            print(f"  WARN  {item_code}: has {sl_count} stock ledger entries. "
                  "Switching to non-stock will keep them but stop new ones.")

        before = item.is_stock_item
        item.is_stock_item = 0
        item.has_batch_no = 0
        item.has_serial_no = 0
        item.include_item_in_manufacturing = 0
        try:
            item.save(ignore_permissions=True)
            print(f"  OK    {item_code}  is_stock_item: {before} -> 0")
            changed += 1
        except Exception as e:
            print(f"  ERROR {item_code}: {e}")

    frappe.db.commit()
    frappe.clear_cache()

    print()
    print(f"  Updated: {changed}    Skipped: {skipped}    Missing: {len(missing)}")
    print()
    print("  Next:")
    print("    1. Hard-refresh POS Awesome (Ctrl+Shift+R) — cached item meta will")
    print("       carry is_stock_item=1 until the page reloads.")
    print("    2. Add the item to the cart — the stock-warning banner should be gone.")
    print("    3. Test the cash <-> qty calculator: type 2000 in Total Amount.")
    print("=" * 70)
    sys.exit(0)


# bench-execute eval-scope fix.
try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
