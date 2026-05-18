"""
Inspect what frappe.get_print actually does on this bench, and try
rendering with the `.print-format` wrapper that Frappe's web rendering
might require.
"""

from __future__ import annotations

import inspect
import frappe


PRINT_FORMAT_NAME = "Sungas Thermal 58mm"


WRAPPED_MARKER_HTML = """
<div class="print-format">
    <h1>ZEBRA_MARKER_42</h1>
    <p>Invoice: {{ doc.name }}</p>
    <p>Customer: {{ doc.customer_name or doc.customer }}</p>
</div>
"""


def main():
    print("=" * 78)
    print(" Inspect get_print + retry with .print-format wrapper")
    print("=" * 78)

    # ----- [1] Show frappe.get_print signature + module -----
    print("\n[1] frappe.get_print module/file:")
    print(f"    module = {frappe.get_print.__module__!r}")
    try:
        print(f"    file   = {inspect.getfile(frappe.get_print)!r}")
        sig = inspect.signature(frappe.get_print)
        print(f"    sig    = {sig}")
    except Exception as exc:
        print(f"    inspect failed: {exc}")

    # ----- [2] Show what utility functions exist in printview -----
    print("\n[2] Public callables in frappe.www.printview:")
    import frappe.www.printview as pv
    for n in sorted(dir(pv)):
        if n.startswith("_"):
            continue
        attr = getattr(pv, n)
        if callable(attr):
            try:
                src_file = inspect.getfile(attr)
                if "frappe" in src_file:
                    print(f"    {n}")
            except Exception:
                pass

    # ----- [3] Wrap html in <div class="print-format"> and retry -----
    print(f"\n[3] Writing WRAPPED html (with .print-format wrapper):")
    frappe.db.sql(
        """UPDATE `tabPrint Format`
           SET html = %s,
               module = 'POSAwesome',
               print_format_type = 'Jinja',
               format_data = NULL,
               raw_printing = 0,
               disabled = 0,
               standard = 'No'
           WHERE name = %s""",
        (WRAPPED_MARKER_HTML, PRINT_FORMAT_NAME),
    )
    frappe.db.commit()
    frappe.clear_cache()
    try:
        frappe.clear_document_cache("Print Format", PRINT_FORMAT_NAME)
    except Exception:
        pass

    cand = frappe.db.get_value("POS Invoice", {"docstatus": 1}, "name", order_by="creation desc")
    if not cand:
        print("    [skip] no POS Invoice")
        return

    print(f"\n[4] Re-rendering POS Invoice {cand!r} with wrapped html:")
    rendered = frappe.get_print("POS Invoice", cand, print_format=PRINT_FORMAT_NAME, as_pdf=False)
    print(f"    length                            : {len(rendered)}")
    print(f"    contains 'ZEBRA_MARKER_42'        : {'ZEBRA_MARKER_42' in rendered}")
    print(f"    contains 'Distributed Discount'   : {'Distributed Discount' in rendered}")

    # ----- [5] Render via PrintView class -----
    print(f"\n[5] Render via frappe.www.printview.PrintView (low-level):")
    try:
        from frappe.www.printview import get_rendered_template
        # get_rendered_template(doc, print_format, meta=None, no_letterhead=None,
        #                       letterhead=None, trigger_print=False, settings=None)
        doc_obj = frappe.get_doc("POS Invoice", cand)
        pf_doc = frappe.get_doc("Print Format", PRINT_FORMAT_NAME)
        html = get_rendered_template(
            doc_obj, print_format=pf_doc,
            no_letterhead=1, trigger_print=False,
        )
        print(f"    length                            : {len(html)}")
        print(f"    contains 'ZEBRA_MARKER_42'        : {'ZEBRA_MARKER_42' in html}")
        print(f"    contains 'Distributed Discount'   : {'Distributed Discount' in html}")
        print(f"    first 400 chars:")
        for line in html[:400].split("\n"):
            print(f"      | {line}")
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
