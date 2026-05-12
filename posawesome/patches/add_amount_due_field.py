"""
Phase 5 — add editable `posa_amount_due` to all POS Awesome item-line doctypes.

Cashier UX (per Sungas cash-change scenario):

    Customer brings \u20a62,000.
    Cashier types 2000 into Amount Due -> qty = 2000 / rate auto-fills.

    OR cashier types qty -> Amount Due = qty * rate auto-fills.

Server-side reconciliation lives in `posawesome.posawesome.api.posa_kg_calc.sync_kg_fields`.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field


ITEM_DOCTYPES = (
    "Sales Invoice Item",
    "POS Invoice Item",
    "Quotation Item",
    "Sales Order Item",
)


def execute():
    for doctype in ITEM_DOCTYPES:
        full_name = f"{doctype}-posa_amount_due"
        if frappe.db.exists("Custom Field", full_name):
            # Idempotent: if the field already exists (older deploy), just
            # force-correct the editability flags rather than skip.
            try:
                cf = frappe.get_doc("Custom Field", full_name)
                cf.read_only = 0
                cf.allow_on_submit = 0
                cf.hidden = 0
                cf.read_only_depends_on = ""
                cf.in_list_view = 1
                cf.columns = 2
                cf.save(ignore_permissions=True)
            except Exception as e:
                frappe.log_error(
                    f"Could not fix {full_name}: {e}",
                    "posawesome.patches.add_amount_due_field",
                )
            continue
        create_custom_field(
            doctype,
            {
                "fieldname": "posa_amount_due",
                "label": "Amount Due (\u20a6)",
                "fieldtype": "Currency",
                "options": "currency",
                "insert_after": "amount",
                "in_list_view": 1,
                "columns": 2,
                "read_only": 0,
                "allow_on_submit": 0,
                "hidden": 0,
                "print_hide": 1,
                "description": (
                    "Editable cashier-facing amount. Edit it to drive qty "
                    "(qty = amount_due / rate). Server reconciles on save."
                ),
            },
        )
