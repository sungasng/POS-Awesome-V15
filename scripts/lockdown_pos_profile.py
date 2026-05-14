"""
Sungas Phase-5: clear `customer` (default customer) on the test POS Profile
so the cashier MUST explicitly pick a customer before they can sell. Combined
with the new front-end validation in invoiceItemMethods.show_payment, this
enforces 'no nameless sales'.

Also keeps posa_allow_user_to_edit_rate=1 (it's now harmless: Rate field is
hard-disabled in the Vue template; the flag now only controls Total Amount,
which we deliberately leave editable for the cashier's cash-change workflow).

Run on bench:
    bench --site sungasmis.v.frappe.cloud execute \\
        "exec(open('/tmp/lockdown_pos_profile.py').read())"
"""

from __future__ import annotations

import sys

import frappe


PROFILES = ("POS - Pedro (Test)",)


def main():
    print("=" * 70)
    print(" Lock down POS Profile(s) — clear default customer, enforce tier-only rates")
    print("=" * 70)
    changed = 0
    for name in PROFILES:
        if not frappe.db.exists("POS Profile", name):
            print(f"  MISS {name}")
            continue
        prof = frappe.get_doc("POS Profile", name)
        before = {
            "customer": prof.customer,
        }
        # Clear the default customer; cashier must pick one each sale.
        prof.customer = ""
        # Keep posa_allow_user_to_edit_rate ON so our Total Amount field
        # remains editable (the Rate field itself is hard-disabled in the
        # Vue template, so this flag no longer puts the cashier in
        # tier-bypass territory).
        prof.posa_allow_user_to_edit_rate = 1
        prof.save(ignore_permissions=True)
        changed += 1
        print(f"  OK   {name}")
        print(f"         customer:                       {before['customer']!r} -> ''")
        print("         posa_allow_user_to_edit_rate:   1 (kept)")

    frappe.db.commit()
    frappe.clear_cache()
    print()
    print(f"  Updated: {changed}")
    print("  Hard-refresh POS Awesome (Ctrl+Shift+R) for the change to take effect.")
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
