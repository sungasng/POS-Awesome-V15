"""
Disable POS profiles that should NOT be used as live POS outlets.

Currently scoped to:
    POS - Bulk Sales Benin   (wholesale -- handled via Sales Invoice, not POS)

The profile is kept (not deleted) so any historical data referencing it
stays intact, but `disabled = 1` prevents cashiers from opening shifts
against it and hides it from the POS profile dropdown.

Run on bench:
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/feat/sungas-customizations/scripts/disable_bulk_sales_pos.py" \\
      -o /tmp/disable_bulk_sales_pos.py && \\
    bench --site sungasmis.v.frappe.cloud execute \\
      "exec(open('/tmp/disable_bulk_sales_pos.py').read())"
"""

from __future__ import annotations

import frappe


PROFILES_TO_DISABLE = [
    "POS - Bulk Sales Benin",
]


def main():
    print("=" * 78)
    print(" Disable non-POS profiles")
    print("=" * 78)

    for profile in PROFILES_TO_DISABLE:
        if not frappe.db.exists("POS Profile", profile):
            print(f"  [SKIP ] {profile!r} not found.")
            continue
        doc = frappe.get_doc("POS Profile", profile)
        if doc.disabled:
            print(f"  [noop ] {profile!r} already disabled.")
            continue
        doc.disabled = 1
        doc.save(ignore_permissions=True)
        print(f"  [DONE ] {profile!r} -> disabled = 1")

    frappe.db.commit()
    print("\n Done.")


try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
