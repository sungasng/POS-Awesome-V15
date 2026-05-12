"""
Fixup patch: ensure posa_amount_due is editable.

The first version of `add_amount_due_field` shipped without explicit
read_only=0 on the Custom Field. On benches where it ran with that
version, the field can render as read-only in the desk Sales Invoice
row editor and (less obviously) on the POS Invoice form.

This patch is a no-op if the field is already editable.
"""

from __future__ import annotations

import frappe


ITEM_DOCTYPES = (
    "Sales Invoice Item",
    "POS Invoice Item",
    "Quotation Item",
    "Sales Order Item",
)


def execute():
    for doctype in ITEM_DOCTYPES:
        name = f"{doctype}-posa_amount_due"
        if not frappe.db.exists("Custom Field", name):
            continue
        try:
            cf = frappe.get_doc("Custom Field", name)
            if (
                cf.read_only
                or cf.hidden
                or cf.read_only_depends_on
                or not cf.in_list_view
            ):
                cf.read_only = 0
                cf.hidden = 0
                cf.read_only_depends_on = ""
                cf.in_list_view = 1
                cf.columns = 2
                cf.save(ignore_permissions=True)
        except Exception as e:
            frappe.log_error(
                f"posa_amount_due editability fix failed for {name}: {e}",
                "posawesome.patches.fix_amount_due_editable",
            )

    # Strip any property setters that pin posa_amount_due read-only.
    for ps in frappe.get_all(
        "Property Setter",
        filters={"field_name": "posa_amount_due"},
        pluck="name",
    ):
        ps_doc = frappe.get_doc("Property Setter", ps)
        if ps_doc.property in ("read_only", "hidden") and str(ps_doc.value) == "1":
            frappe.delete_doc(
                "Property Setter", ps, force=1, ignore_permissions=True
            )

    frappe.db.commit()
    frappe.clear_cache()
