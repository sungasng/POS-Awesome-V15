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
            continue
        create_custom_field(
            doctype,
            {
                "fieldname": "posa_amount_due",
                "label": "Amount Due (\u20a6)",
                "fieldtype": "Currency",
                "options": "currency",
                "insert_after": "amount",
                "in_list_view": 0,
                "print_hide": 1,
                "description": (
                    "Editable cashier-facing amount. Edit it to drive qty "
                    "(qty = amount_due / rate). Server reconciles on save."
                ),
            },
        )
