"""
Bulk-set Customer.default_price_list = 'SCL Standard Selling' for every
customer that doesn't already have one.

Carryover P0 from the previous fork:
    Without default_price_list, POS Awesome shows pre-save Sales Invoice
    rate as \u20a60.00 instead of the standard list rate. After save, the
    tier overrides anyway -- but the cashier sees \u20a60.00 in between,
    which causes confusion.

Idempotent. Run on bench:
    bench --site sungasmis.v.frappe.cloud execute \\
        "exec(open('/tmp/fix_default_price_list.py').read())"
"""

from __future__ import annotations

import sys

import frappe


TARGET_PRICE_LIST = "SCL Standard Selling"


def main():
    print("=" * 70)
    print(f" Set Customer.default_price_list = {TARGET_PRICE_LIST!r}")
    print("=" * 70)

    if not frappe.db.exists("Price List", TARGET_PRICE_LIST):
        print(f"  ERROR: Price List {TARGET_PRICE_LIST!r} not found.")
        sys.exit(1)

    # Count first so we can report what we're about to do.
    targets = frappe.get_all(
        "Customer",
        filters=[
            ["default_price_list", "in", (None, "")],
        ],
        pluck="name",
    )
    print(f"  Customers missing default_price_list: {len(targets)}")

    if not targets:
        print("  Nothing to do; every customer already has a default price list.")
        sys.exit(0)

    # Direct SQL is dramatically faster than frappe.set_value() x 8,000+ rows.
    # We deliberately bypass the framework here because there are no hooks
    # on Customer.default_price_list and we want a single atomic UPDATE.
    frappe.db.sql(
        """
        UPDATE `tabCustomer`
        SET default_price_list = %(pl)s,
            modified = NOW(),
            modified_by = %(user)s
        WHERE default_price_list IS NULL OR default_price_list = ''
        """,
        {"pl": TARGET_PRICE_LIST, "user": frappe.session.user or "Administrator"},
    )
    frappe.db.commit()
    frappe.clear_cache()

    after = frappe.db.count("Customer", {"default_price_list": ["in", (None, "")]})
    updated = len(targets) - after
    print(f"  Updated: {updated}")
    print(f"  Still missing (shouldn't happen): {after}")

    print()
    print("=" * 70)
    sys.exit(0 if after == 0 else 1)


try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
