"""
Isolate the root cause: replace Sungas Thermal 58mm's html with a
trivially small Jinja template ("HELLO_FROM_SUNGAS_TEMPLATE"). If the
server-render output then contains that marker, our previous Jinja
had a hidden syntax error and Frappe was silently falling back to
Standard. If the server-render output STILL contains 'Distributed
Discount', there's a hook intercepting print rendering for POS
Invoice -- we'll need to inspect hooks.py / Print Settings.

Also greps the on-disk app for any `pos_invoice` print override hook.

Run on bench:
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/feat/sungas-customizations/scripts/minimal_template_test.py" \\
      -o /tmp/minimal_template_test.py && \\
    bench --site sungasmis.v.frappe.cloud execute \\
      "exec(open('/tmp/minimal_template_test.py').read())"
"""

from __future__ import annotations

import os
import frappe


PRINT_FORMAT_NAME = "Sungas Thermal 58mm"
MARKER = "HELLO_FROM_SUNGAS_MARKER_42"


MINIMAL_HTML = """
<div>{{ "%s" }}</div>
<div>Invoice: {{ doc.name }}</div>
<div>Customer: {{ doc.customer_name or doc.customer }}</div>
""" % MARKER


def main():
    print("=" * 78)
    print(" Minimal-template isolation test")
    print("=" * 78)

    # ----- 1. Force the html to a trivial template -----
    frappe.db.set_value(
        "Print Format", PRINT_FORMAT_NAME,
        {
            "html": MINIMAL_HTML,
            "css": "body{font-size:10pt;}",
            "print_format_type": "Jinja",
            "format_data": None,
            "raw_printing": 0,
            "disabled": 0,
            "standard": "No",
            "module": None,
        },
    )
    frappe.db.commit()
    frappe.clear_cache()
    try:
        frappe.clear_document_cache("Print Format", PRINT_FORMAT_NAME)
    except Exception:
        pass

    print(f"\n[1] Set html to minimal template (size={len(MINIMAL_HTML)})")
    print(f"    Looking for marker {MARKER!r} in render output...")

    # ----- 2. Render -----
    cand = frappe.db.get_value("POS Invoice", {"docstatus": 1}, "name", order_by="creation desc")
    if not cand:
        print("    [WARN] no submitted POS Invoice to test against")
        return

    rendered = frappe.get_print("POS Invoice", cand, print_format=PRINT_FORMAT_NAME, as_pdf=False)
    has_marker = MARKER in rendered
    has_standard = "Distributed Discount" in rendered
    print(f"    contains {MARKER!r}        : {has_marker}")
    print(f"    contains 'Distributed Discount' : {has_standard}")

    if has_marker and not has_standard:
        print("\n  ⇒ DIAGNOSIS: minimal template IS rendering. The previous")
        print("     Sungas html had a silent Jinja error. Will rebuild it")
        print("     incrementally to find the offending block.")
    elif not has_marker and has_standard:
        print("\n  ⇒ DIAGNOSIS: marker is NOT in render even with minimal html.")
        print("     A hook is intercepting print rendering for POS Invoice.")
        print("     Looking for the override now...")
    else:
        print("\n  ⇒ DIAGNOSIS: weird state -- both/neither markers found.")

    # ----- 3. Hunt for print-related hooks in installed apps -----
    print("\n[2] Searching app hooks.py / py files for POS Invoice print overrides:")

    interesting_patterns = [
        "before_print",
        "after_print",
        "before_print_render",
        "print_format_html",
        "render_print_format",
        "pos_invoice_print",
        "override_doctype_class",
    ]

    apps_dir = frappe.get_app_path("frappe").rsplit("/frappe", 1)[0]
    found_any = False
    for app in os.listdir(apps_dir):
        app_path = os.path.join(apps_dir, app)
        hooks_path = os.path.join(app_path, app, "hooks.py")
        if not os.path.isfile(hooks_path):
            continue
        try:
            content = open(hooks_path, "r").read()
        except Exception:
            continue
        for pat in interesting_patterns:
            if pat in content:
                # Print a small window around the match
                for line_no, line in enumerate(content.split("\n"), 1):
                    if pat in line:
                        print(f"    {app}/hooks.py:{line_no:>4}  {line.strip()[:120]}")
                        found_any = True
    if not found_any:
        print("    (no relevant print hooks found in any app)")

    print("\n[3] Looking for on-disk Sungas Thermal print_format folders:")
    found_files = False
    for app in os.listdir(apps_dir):
        app_path = os.path.join(apps_dir, app)
        for root, dirs, files in os.walk(app_path):
            for fn in files:
                lower = fn.lower()
                if "sungas" in lower or "thermal" in lower or "58mm" in lower:
                    print(f"    {os.path.relpath(os.path.join(root, fn), apps_dir)}")
                    found_files = True
    if not found_files:
        print("    (no on-disk file mentioning Sungas/Thermal/58mm)")


try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
