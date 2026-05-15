"""
Server-side ₦ ↔ Kg / Amount-Due sync.

Business rule (per Sungas cash-change scenario):

    Customer hands over ₦2,000 -> cashier needs the qty (kg) that ₦2,000 buys.
    OR cashier types qty (kg)  -> system computes ₦ to collect.

Because the bulk-gas Item has:
    stock_uom         = "Kg"
    Price-list rate   = ₦/Kg

we get a 1-step relation:

    posa_amount_due = qty * rate
    qty             = posa_amount_due / rate    (when rate > 0)

This module reconciles `posa_amount_due` and `qty` on every validate so
either direction the cashier edits, the other side stays consistent.

Edit-detection rule:
    If `posa_amount_due` is set AND differs from `qty * rate` AND rate > 0,
    we treat it as a cashier-driven amount-edit and rewrite qty.
    Otherwise we treat qty as authoritative and rewrite posa_amount_due.

Backward-compat:
    The legacy fields `posa_kg_qty` and `posa_rate_per_kg` (added in the
    earlier kg-calc patch) are kept for display purposes:
        - posa_kg_qty      mirrors qty   (since stock_uom == Kg, they're equal)
        - posa_rate_per_kg mirrors rate  (since rate is already ₦/Kg)
    They have no business logic of their own anymore.
"""

from __future__ import annotations

import frappe
from frappe.utils import flt


# Qty precision: physical dispensers at Sungas read 2 decimal places (e.g.
# 0.01 kg increments). Storing more precision lies to the cashier about
# what the dispenser can actually deliver.
QTY_PRECISION = 2
# Money precision — NGN to kobo.
AMOUNT_PRECISION = 2
# Tolerance for "amount drifted" detection (avoid float jitter).
AMOUNT_TOLERANCE = 0.01


def sync_kg_fields(doc, method=None):
    """
    Reconcile posa_amount_due and qty on each item row.

    Direction:
        cashier edited amount  -> rewrite qty
        cashier edited qty     -> rewrite amount  (also covers the initial state)

    Called from Sales Invoice / POS Invoice / Quotation / Sales Order validate,
    AFTER `apply_tiered_pricing` so `rate` is already final.
    """
    items = getattr(doc, "items", None) or []
    any_qty_changed = False

    for row in items:
        rate = flt(getattr(row, "rate", 0) or 0)
        qty = flt(getattr(row, "qty", 0) or 0)
        amount_due = flt(getattr(row, "posa_amount_due", 0) or 0)
        computed = flt(qty * rate, AMOUNT_PRECISION)

        amount_edited = (
            amount_due > 0
            and rate > 0
            and abs(amount_due - computed) > AMOUNT_TOLERANCE
        )

        if amount_edited:
            # Cashier typed \u20a6 -- recompute qty from amount.
            # ROUND DOWN to 2 decimals: the dispenser delivers 0.01 kg
            # increments, so we give the customer the largest qty their cash
            # buys without going over. The difference (e.g. \u20a620 on a
            # \u20a62,000 cash payment) is booked as a Rounding Adjustment to
            # the Company's round-off account by `apply_cash_overage`.
            import math
            new_qty = math.floor((amount_due / rate) * 100) / 100
            if new_qty != qty:
                row.qty = new_qty
                qty = new_qty
                any_qty_changed = True
            # KEEP posa_amount_due as the cashier's typed value. The overage
            # post-processor reads it to compute the rounding line.
            row.posa_amount_due = flt(amount_due, AMOUNT_PRECISION)
        else:
            # Qty (or rate) is authoritative — mirror into amount_due.
            row.posa_amount_due = computed

        # Legacy display mirrors (stock_uom is Kg → kg_qty == qty, rate_per_kg == rate).
        if hasattr(row, "posa_kg_qty"):
            row.posa_kg_qty = flt(qty, QTY_PRECISION)
        if hasattr(row, "posa_rate_per_kg"):
            row.posa_rate_per_kg = flt(rate, AMOUNT_PRECISION)

    if any_qty_changed and hasattr(doc, "calculate_taxes_and_totals"):
        doc.calculate_taxes_and_totals()


@frappe.whitelist()
def get_item_weight(item_code: str) -> dict:
    """
    Backward-compat: legacy POS Awesome / mobile clients still call this.
    Returns the Item's weight_per_unit/weight_uom metadata. The amount-due
    feature no longer depends on it, but we keep the endpoint stable.
    """
    if not item_code:
        return {"item_code": "", "weight_per_unit": 0, "weight_uom": "", "is_kg": False}
    row = frappe.db.get_value(
        "Item",
        item_code,
        ["weight_per_unit", "weight_uom"],
        as_dict=True,
    ) or {}
    wpu = flt(row.get("weight_per_unit") or 0)
    wuom = row.get("weight_uom") or ""
    return {
        "item_code": item_code,
        "weight_per_unit": wpu,
        "weight_uom": wuom,
        "is_kg": wuom == "Kg" and wpu > 0,
    }
