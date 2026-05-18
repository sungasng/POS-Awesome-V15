"""
Definitive diagnostic: render the Sungas Thermal 58mm format server-side
using frappe.get_print() and dump the first/last 800 bytes of the rendered
HTML. This tells us whether the saved html actually gets used by the
renderer.

Also bumps the Print Format's `modified` timestamp so any caching layer
keyed on mtime invalidates.

Run on bench:
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/feat/sungas-customizations/scripts/diagnose_print_render.py" \\
      -o /tmp/diagnose_print_render.py && \\
    bench --site sungasmis.v.frappe.cloud execute \\
      "exec(open('/tmp/diagnose_print_render.py').read())"
"""

from __future__ import annotations

import frappe
from frappe.utils.pdf import get_pdf


PRINT_FORMAT_NAME = "Sungas Thermal 58mm"


def main():
    print("=" * 78)
    print(f" Diagnose {PRINT_FORMAT_NAME!r} render")
    print("=" * 78)

    pf = frappe.get_doc("Print Format", PRINT_FORMAT_NAME)
    print(f"\n[1] Print Format meta:")
    print(f"    name              = {pf.name!r}")
    print(f"    doc_type          = {pf.doc_type!r}")
    print(f"    print_format_type = {pf.print_format_type!r}")
    print(f"    standard          = {pf.standard!r}")
    print(f"    disabled          = {pf.disabled!r}")
    print(f"    raw_printing      = {pf.raw_printing!r}")
    print(f"    format_data       = {(str(pf.format_data)[:50] if pf.format_data else None)!r}")
    print(f"    html size         = {len(pf.html or '')}")
    print(f"    css size          = {len(pf.css or '')}")
    print(f"    html[:300]        = {(pf.html or '')[:300]!r}")

    # Find one POS Invoice to render against.
    candidate = frappe.db.get_value(
        "POS Invoice",
        {"docstatus": 1},
        "name",
        order_by="creation desc",
    )
    if not candidate:
        print("\n  [WARN] no submitted POS Invoice found -- cannot test render.")
        return

    print(f"\n[2] Rendering POS Invoice {candidate!r} through frappe.get_print():")
    try:
        rendered = frappe.get_print(
            "POS Invoice",
            candidate,
            print_format=PRINT_FORMAT_NAME,
            as_pdf=False,
        )
        print(f"    rendered length = {len(rendered)}")
        print(f"    contains 'SUNGAS COMPANY LIMITED' : {'SUNGAS COMPANY LIMITED' in rendered}")
        print(f"    contains 'Receipt No:'            : {'Receipt No:' in rendered}")
        print(f"    contains 'Distributed Discount'   : {'Distributed Discount' in rendered}")
        print(f"    contains 'POS Offers'             : {'POS Offers' in rendered}")
        print(f"    contains 'Terms &amp; Conditions' : {'Terms &amp; Conditions' in rendered}")
        print(f"    contains 'Eligible for Commission': {'Eligible for Commission' in rendered}")

        print(f"\n[3] First 800 bytes of rendered HTML:")
        print("-" * 78)
        print(rendered[:800])
        print("-" * 78)
        print(f"\n[4] Last 800 bytes of rendered HTML:")
        print("-" * 78)
        print(rendered[-800:])
        print("-" * 78)
    except Exception as exc:
        print(f"    [ERROR] render failed: {exc}")
        import traceback
        traceback.print_exc()

    # Bump modified timestamp to bust any mtime caches.
    frappe.db.set_value(
        "Print Format", PRINT_FORMAT_NAME, "modified",
        frappe.utils.now(), update_modified=False,
    )
    frappe.clear_cache(doctype="Print Format")
    frappe.clear_document_cache("Print Format", PRINT_FORMAT_NAME)
    frappe.db.commit()
    print("\n[5] Bumped modified timestamp + cleared doctype cache. Done.")


try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
