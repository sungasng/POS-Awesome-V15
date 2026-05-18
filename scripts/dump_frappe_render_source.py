"""
Final diagnostic: dump the actual Frappe source for get_rendered_template
so we can see why it's bypassing our Jinja html. Also test the rawest
possible render: frappe.render_template(pf.html, {"doc": ...}).

Run on bench:
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/feat/sungas-customizations/scripts/dump_frappe_render_source.py" \\
      -o /tmp/dump_frappe_render_source.py && \\
    bench --site sungasmis.v.frappe.cloud execute \\
      "exec(open('/tmp/dump_frappe_render_source.py').read())"
"""

from __future__ import annotations

import inspect
import frappe


PRINT_FORMAT_NAME = "Sungas Thermal 58mm"


def main():
    print("=" * 78)
    print(" Frappe get_rendered_template source dump")
    print("=" * 78)

    # ----- [1] Show the actual source of get_rendered_template -----
    from frappe.www.printview import get_rendered_template
    print("\n[1] Source of frappe.www.printview.get_rendered_template:")
    print("-" * 78)
    try:
        src = inspect.getsource(get_rendered_template)
        for i, line in enumerate(src.split("\n"), 1):
            print(f"  {i:>3} | {line}")
    except Exception as exc:
        print(f"  failed: {exc}")
    print("-" * 78)

    # ----- [2] Rawest Jinja render -- bypass all Frappe print dispatch -----
    print("\n[2] Rawest possible render via frappe.render_template():")
    pf = frappe.get_doc("Print Format", PRINT_FORMAT_NAME)
    cand = frappe.db.get_value("POS Invoice", {"docstatus": 1}, "name", order_by="creation desc")
    if not cand:
        print("    [skip] no POS Invoice")
        return

    doc_obj = frappe.get_doc("POS Invoice", cand)
    try:
        out = frappe.render_template(pf.html, {"doc": doc_obj})
        print(f"    html input length            : {len(pf.html or '')}")
        print(f"    rendered output length       : {len(out)}")
        print(f"    contains 'ZEBRA_MARKER_42'   : {'ZEBRA_MARKER_42' in out}")
        print(f"    contains 'Distributed Discount': {'Distributed Discount' in out}")
        print(f"    first 400 chars of output:")
        for ln in out[:400].split("\n"):
            print(f"      | {ln}")
    except Exception as exc:
        print(f"    EXCEPTION: {type(exc).__name__}: {exc}")
        import traceback
        traceback.print_exc()


try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
