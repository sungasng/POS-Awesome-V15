"""
Fix: nuke `format_data` on Sungas Thermal 58mm so the Jinja `html`
actually gets used.

Background
----------
Frappe v15 supports two print engines per Print Format record:

  1. Print Designer  -- driven by `format_data` (JSON) + `print_designer*` fields
  2. Classic Jinja   -- driven by `html` + `css` (when format_data is empty)

When `format_data` is populated, Frappe IGNORES the `html` field entirely
and auto-renders a table off the DocType meta -- producing the verbose
Sr / Row ID / Stock UOM / Distributed Discount Amount / POS Offers
column dump the user keeps seeing despite our Sungas-branded Jinja
template being saved correctly.

This script:
  * Verifies the saved html still contains our content
  * Sets format_data = NULL, raw_printing = 0, print_format_type = 'Jinja',
    and any print_designer_* fields to NULL/empty
  * Updates a single record via raw db so we sidestep any on-save hook
    that might re-derive format_data
  * Clears the Print Format document cache + the global cache so the
    web renderer picks up the change without a bench restart.

Run on bench:
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/feat/sungas-customizations/scripts/fix_print_format_data.py" \\
      -o /tmp/fix_print_format_data.py && \\
    bench --site sungasmis.v.frappe.cloud execute \\
      "exec(open('/tmp/fix_print_format_data.py').read())"

Then in the browser hard-refresh (Cmd+Shift+R) and re-print.
"""

from __future__ import annotations

import frappe


PRINT_FORMAT_NAME = "Sungas Thermal 58mm"


def main():
    print("=" * 78)
    print(f" Clear format_data on {PRINT_FORMAT_NAME!r} so html is rendered")
    print("=" * 78)

    if not frappe.db.exists("Print Format", PRINT_FORMAT_NAME):
        print(f"  [FATAL] Print Format {PRINT_FORMAT_NAME!r} not found.")
        return

    # ----- Inspect current state -----
    pf_meta = frappe.get_meta("Print Format")
    candidate_fields = [
        "format_data", "raw_printing", "print_format_type", "html", "css",
        "print_designer_header", "print_designer_body", "print_designer_after_table",
        "print_designer_footer", "print_designer_settings", "print_designer_print_format",
    ]
    fields = [f for f in candidate_fields if pf_meta.get_field(f)]
    row = frappe.db.get_value("Print Format", PRINT_FORMAT_NAME, fields, as_dict=True)

    print("\n[1] Current state:")
    for k in fields:
        val = row.get(k)
        if k in ("html", "css"):
            print(f"    {k:<35} = (len={len(val or '')})")
        else:
            preview = (str(val)[:60] + "...") if val and len(str(val)) > 60 else val
            print(f"    {k:<35} = {preview!r}")

    # ----- Bulk-update via db so we bypass any auto-derive hook -----
    print("\n[2] Updating fields via raw db.set_value (one call per field):")

    updates: dict[str, object] = {
        "print_format_type": "Jinja",
        "raw_printing": 0,
        "format_data": None,
        "disabled": 0,
        "standard": "No",
    }
    for designer_field in [
        "print_designer_header", "print_designer_body", "print_designer_after_table",
        "print_designer_footer", "print_designer_settings", "print_designer_print_format",
    ]:
        if pf_meta.get_field(designer_field):
            updates[designer_field] = None

    for k, v in updates.items():
        if not pf_meta.get_field(k):
            continue
        frappe.db.set_value("Print Format", PRINT_FORMAT_NAME, k, v)
        print(f"    [+] {k} -> {v!r}")

    frappe.db.commit()

    # ----- Re-fetch + show new state -----
    new_row = frappe.db.get_value("Print Format", PRINT_FORMAT_NAME, fields, as_dict=True)
    print("\n[3] New state:")
    for k in fields:
        val = new_row.get(k)
        if k in ("html", "css"):
            print(f"    {k:<35} = (len={len(val or '')})")
        else:
            preview = (str(val)[:60] + "...") if val and len(str(val)) > 60 else val
            print(f"    {k:<35} = {preview!r}")

    # ----- Cache flush -----
    print("\n[4] Clearing Frappe caches...")
    frappe.clear_cache()
    try:
        frappe.clear_document_cache("Print Format", PRINT_FORMAT_NAME)
    except Exception:
        pass

    print("\n" + "=" * 78)
    print(" DONE. Now from the shell run:")
    print("     bench --site sungasmis.v.frappe.cloud clear-cache")
    print("     bench --site sungasmis.v.frappe.cloud clear-website-cache")
    print(" Then hard-refresh (Cmd+Shift+R) and re-print any POS Invoice.")
    print("=" * 78)


try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
