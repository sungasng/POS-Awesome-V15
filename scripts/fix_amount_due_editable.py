"""
Quick fix for posa_amount_due: ensure the custom field is editable.

When Frappe creates a Currency Custom Field via insert_after on a doctype
whose neighbor (`amount`) is read-only / calculated, the new field can
inherit read_only=1. This script forces read_only=0 across all four
item-line doctypes and clears any related property-setter overrides.

Run on bench:
    bench --site sungasmis.v.frappe.cloud execute \\
        "exec(open('/tmp/fix_amount_due_editable.py').read())"
"""

from __future__ import annotations

import sys

import frappe


ITEM_DOCTYPES = (
    "Sales Invoice Item",
    "POS Invoice Item",
    "Quotation Item",
    "Sales Order Item",
)


def main():
    print("=" * 60)
    print("Fix: make posa_amount_due editable")
    print("=" * 60)
    changed = 0
    for doctype in ITEM_DOCTYPES:
        name = f"{doctype}-posa_amount_due"
        if not frappe.db.exists("Custom Field", name):
            print(f"  SKIP {name}: custom field not found (run migrate first)")
            continue

        cf = frappe.get_doc("Custom Field", name)
        before = {
            "read_only": cf.read_only,
            "allow_on_submit": cf.allow_on_submit,
            "hidden": cf.hidden,
            "depends_on": cf.depends_on,
            "read_only_depends_on": cf.read_only_depends_on,
        }
        cf.read_only = 0
        cf.allow_on_submit = 0
        cf.hidden = 0
        cf.read_only_depends_on = ""
        cf.in_list_view = 1   # also surface it inline so cashier sees it without expanding
        cf.columns = 2
        cf.save(ignore_permissions=True)
        after = {
            "read_only": cf.read_only,
            "allow_on_submit": cf.allow_on_submit,
            "hidden": cf.hidden,
            "depends_on": cf.depends_on,
            "read_only_depends_on": cf.read_only_depends_on,
            "in_list_view": cf.in_list_view,
        }
        print(f"  OK   {name}")
        print(f"         before: {before}")
        print(f"         after:  {after}")
        changed += 1

    # Clear any property setters that might override read_only on this field
    cleared = 0
    for ps in frappe.get_all(
        "Property Setter",
        filters={"field_name": "posa_amount_due"},
        pluck="name",
    ):
        ps_doc = frappe.get_doc("Property Setter", ps)
        if ps_doc.property in ("read_only", "hidden") and ps_doc.value in ("1", 1, True):
            print(f"  DELETE Property Setter {ps} ({ps_doc.property}={ps_doc.value})")
            frappe.delete_doc("Property Setter", ps, force=1, ignore_permissions=True)
            cleared += 1

    frappe.db.commit()
    frappe.clear_cache()
    print(f"\n  Updated {changed} custom field(s), removed {cleared} property setter(s).")
    print("  Hard-refresh the browser (Ctrl+Shift+R) for the desk form to pick up the change.")
    print("=" * 60)
    sys.exit(0)


main()
