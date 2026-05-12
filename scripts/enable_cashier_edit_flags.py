"""
Enable the cashier-friendly toggles on POS Profile(s) so:
    - Rate is editable (required for our Total Amount-driven calc)
    - Item discount is editable
    - Additional discount is editable
    - Inline qty edit works

Defaults to patching ONLY 'POS - Pedro (Test)'. Edit PROFILES below to
patch more.

Run on bench:
    bench --site sungasmis.v.frappe.cloud execute \\
        "exec(open('/tmp/enable_cashier_edit_flags.py').read())"
"""

from __future__ import annotations

import sys

import frappe


PROFILES = (
    "POS - Pedro (Test)",
)

# Field -> desired value. All POS-Awesome side toggles that affect editability.
FIELDS = {
    "posa_allow_user_to_edit_rate": 1,
    "posa_allow_user_to_edit_item_discount": 1,
    "posa_allow_user_to_edit_additional_discount": 1,
    "posa_input_qty": 1,
    "posa_allow_delete": 1,
    "posa_allow_print_draft_invoices": 1,
}


def main():
    print("=" * 70)
    print(" Enable cashier edit flags on POS Profile(s)")
    print("=" * 70)
    changed = 0

    for name in PROFILES:
        if not frappe.db.exists("POS Profile", name):
            print(f"  MISS {name}: not found")
            continue
        prof = frappe.get_doc("POS Profile", name)
        diffs = []
        for field, val in FIELDS.items():
            try:
                current = getattr(prof, field, None)
            except Exception:
                current = None
            if current != val:
                diffs.append((field, current, val))
                setattr(prof, field, val)
        if diffs:
            prof.save(ignore_permissions=True)
            changed += 1
            print(f"  OK   {name}")
            for f, before, after in diffs:
                print(f"         {f}: {before} -> {after}")
        else:
            print(f"  SKIP {name}: already configured")

    frappe.db.commit()
    frappe.clear_cache()

    print()
    print(f"  Updated: {changed}")
    print()
    print("  Next:")
    print("    1. Hard-refresh POS Awesome (Ctrl+Shift+R)")
    print("    2. Expand the LPG row in the cart")
    print("    3. Total Amount should now be editable (white, not grey)")
    print("    4. Type 2000 -> qty should drop to ~1.471")
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
