"""
Last-resort comprehensive diagnostic:

1. Direct raw SQL dump of the tabPrint Format row to see the actual
   stored field values (no ORM caching, no field stripping).
2. Set module = 'POSAwesome' (a known-valid module on this site).
3. Try THREE different render paths and compare:
     - frappe.get_print()                                     (bench API)
     - frappe.utils.print_format.read_multi_pdf()             (Frappe core)
     - frappe.www.printview.get_html()                        (web endpoint)
   Print the first 400 chars of each result so we can see exactly
   which path is broken.
4. Use raw SQL to confirm the html column is the marker template.

Run:
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/feat/sungas-customizations/scripts/multi_path_print_test.py" \\
      -o /tmp/multi_path_print_test.py && \\
    bench --site sungasmis.v.frappe.cloud execute \\
      "exec(open('/tmp/multi_path_print_test.py').read())"
"""

from __future__ import annotations

import frappe


PRINT_FORMAT_NAME = "Sungas Thermal 58mm"
MARKER = "ZEBRA_MARKER_42"
MARKER_HTML = f"<div>{MARKER}</div><div>Invoice: {{{{ doc.name }}}}</div>"


def main():
    print("=" * 78)
    print(" Multi-path print render diagnostic")
    print("=" * 78)

    # ----- [1] Raw SQL row dump (no ORM) -----
    print("\n[1] Raw SQL row dump for Print Format:")
    rows = frappe.db.sql(
        """SELECT name, doc_type, print_format_type, standard, disabled,
                  raw_printing, module,
                  CHAR_LENGTH(html) AS html_len,
                  CHAR_LENGTH(css)  AS css_len,
                  CHAR_LENGTH(format_data) AS fd_len,
                  LEFT(html, 200) AS html_head
           FROM `tabPrint Format`
           WHERE name = %s""",
        (PRINT_FORMAT_NAME,),
        as_dict=True,
    )
    if not rows:
        print(f"    [FATAL] no row with name = {PRINT_FORMAT_NAME!r}")
        return
    for k, v in rows[0].items():
        print(f"    {k:<20} = {v!r}")

    # ----- [2] Force-set module = 'POSAwesome' (valid module) -----
    print(f"\n[2] Force-write module + minimal Jinja html via raw SQL:")
    frappe.db.sql(
        """UPDATE `tabPrint Format`
           SET module = 'POSAwesome',
               html = %s,
               print_format_type = 'Jinja',
               standard = 'No',
               disabled = 0,
               raw_printing = 0,
               format_data = NULL
           WHERE name = %s""",
        (MARKER_HTML, PRINT_FORMAT_NAME),
    )
    frappe.db.commit()
    frappe.clear_cache()
    try:
        frappe.clear_document_cache("Print Format", PRINT_FORMAT_NAME)
    except Exception:
        pass
    print(f"    DONE")

    # Re-fetch to confirm SQL changes stuck
    confirm = frappe.db.sql(
        "SELECT module, LEFT(html, 100) AS h FROM `tabPrint Format` WHERE name=%s",
        (PRINT_FORMAT_NAME,),
        as_dict=True,
    )[0]
    print(f"    confirm: module={confirm['module']!r}, html_head={confirm['h']!r}")

    # ----- [3] Find an invoice to render -----
    cand = frappe.db.get_value("POS Invoice", {"docstatus": 1}, "name", order_by="creation desc")
    if not cand:
        print("\n    [WARN] no POS Invoice available -- skipping render tests")
        return
    print(f"\n[3] Rendering POS Invoice {cand!r} via three paths:")

    # Path A: frappe.get_print
    print("\n  ---- Path A: frappe.get_print() ----")
    try:
        out_a = frappe.get_print(
            "POS Invoice", cand,
            print_format=PRINT_FORMAT_NAME, as_pdf=False,
        )
        print(f"    length         : {len(out_a)}")
        print(f"    contains {MARKER!r}: {MARKER in out_a}")
        print(f"    contains 'Distributed Discount': {'Distributed Discount' in out_a}")
        print(f"    first 400 chars:")
        print("    >>> " + (out_a[:400].replace('\n', '\n    >>> ')))
    except Exception as exc:
        print(f"    EXCEPTION: {type(exc).__name__}: {exc}")

    # Path B: frappe.www.printview.get_html
    print("\n  ---- Path B: frappe.www.printview.get_html() ----")
    try:
        from frappe.www.printview import get_html
        out_b = get_html("POS Invoice", cand, print_format=PRINT_FORMAT_NAME)
        print(f"    length         : {len(out_b)}")
        print(f"    contains {MARKER!r}: {MARKER in out_b}")
        print(f"    contains 'Distributed Discount': {'Distributed Discount' in out_b}")
        print(f"    first 400 chars:")
        print("    >>> " + (out_b[:400].replace('\n', '\n    >>> ')))
    except Exception as exc:
        print(f"    EXCEPTION: {type(exc).__name__}: {exc}")

    # Path C: explicit get_print with html override (bypass PF lookup entirely)
    print("\n  ---- Path C: get_print(html='<h1>OVERRIDE</h1>', no print_format) ----")
    try:
        out_c = frappe.get_print(
            "POS Invoice", cand,
            html="<h1>OVERRIDE_MARKER</h1>",
            as_pdf=False,
        )
        print(f"    length            : {len(out_c)}")
        print(f"    contains 'OVERRIDE_MARKER': {'OVERRIDE_MARKER' in out_c}")
        print(f"    contains 'Distributed Discount': {'Distributed Discount' in out_c}")
    except Exception as exc:
        print(f"    EXCEPTION: {type(exc).__name__}: {exc}")

    # Path D: lookup the PF via Frappe's get_print_format_doc helper
    print("\n  ---- Path D: frappe.www.printview.get_print_format_doc() lookup ----")
    try:
        from frappe.www.printview import get_print_format_doc
        meta = frappe.get_meta("POS Invoice")
        pfd = get_print_format_doc(PRINT_FORMAT_NAME, meta)
        print(f"    returned : {type(pfd).__name__}")
        if pfd:
            print(f"    name     : {pfd.name!r}")
            print(f"    doc_type : {pfd.doc_type!r}")
            print(f"    pf_type  : {pfd.print_format_type!r}")
            print(f"    html len : {len(pfd.html or '')}")
            print(f"    html head: {(pfd.html or '')[:200]!r}")
        else:
            print(f"    <- returned None! that's why Standard is rendered")
    except Exception as exc:
        print(f"    EXCEPTION: {type(exc).__name__}: {exc}")


try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
