"""
Phase-5 Sungas: book cash overage as a Rounding Adjustment on the invoice.

Business rule (locked 2026-02-12):
    - Dispenser delivers 0.01 kg increments.
    - Customer hands cash (e.g. \u20a62,000).
    - Cashier types \u20a62,000 in Total Amount.
    - System computes qty = floor(2,000 / 3,000 \xd7 100) / 100 = 0.66 kg
      -> goods value = 0.66 \xd7 3,000 = \u20a61,980.
    - Difference \u20a620 is booked as Rounding Adjustment to the Company's
      round-off account (e.g. 'Round Off Expense - SCL') so the customer
      pays exactly what they handed over, with no physical change owed.

Direction: OVER ONLY.
    - If cashier-typed amount > goods value -> overage line added.
    - If cashier-typed amount <= goods value -> NO adjustment (cashier
      either matches exactly, OR is rounding-down with change available).
"""

from __future__ import annotations

import frappe
from frappe.utils import flt


# Tolerance for floating-point comparisons (kobo precision).
TOLERANCE = 0.01


def apply_cash_overage(doc, method=None):
    """
    Compute total cash overage across all rows and book it as a Rounding
    Adjustment so doc.rounded_total == sum of cashier-typed amounts.

    Hooked into Sales Invoice / POS Invoice validate AFTER sync_kg_fields
    (which leaves posa_amount_due as the cashier's typed cash amount).
    """
    if not getattr(doc, "items", None):
        return

    total_overage = 0.0
    for row in doc.items:
        amount_due = flt(getattr(row, "posa_amount_due", 0) or 0)
        rate = flt(getattr(row, "rate", 0) or 0)
        qty = flt(getattr(row, "qty", 0) or 0)
        goods_value = flt(qty * rate, 2)
        diff = flt(amount_due - goods_value, 2)
        # OVER ONLY: only if cashier typed MORE than goods value.
        if diff > TOLERANCE:
            total_overage += diff

    total_overage = flt(total_overage, 2)

    # Always reset to a clean state on re-validate so a previous overage
    # doesn't leak into a different scenario (e.g. cashier edits qty after
    # typing amount).
    doc.rounding_adjustment = 0
    if hasattr(doc, "base_rounding_adjustment"):
        doc.base_rounding_adjustment = 0

    if total_overage < TOLERANCE:
        # Let ERPNext's standard rounding logic resume normal behavior.
        return

    # Enable rounding so the field is honored, then set the adjustment.
    doc.disable_rounded_total = 0
    doc.rounding_adjustment = total_overage
    if hasattr(doc, "base_rounding_adjustment"):
        doc.base_rounding_adjustment = total_overage

    grand_total = flt(getattr(doc, "grand_total", 0) or 0)
    doc.rounded_total = flt(grand_total + total_overage, 2)
    if hasattr(doc, "base_rounded_total"):
        doc.base_rounded_total = doc.rounded_total

    # Recompute outstanding so the payment screen sees the rounded_total.
    if hasattr(doc, "outstanding_amount"):
        paid = flt(getattr(doc, "paid_amount", 0) or 0)
        doc.outstanding_amount = flt(doc.rounded_total - paid, 2)

    # Phase-5 Sungas: suppress Frappe's auto-computed change_amount /
    # write_off_amount. Without this, Frappe sees paid_amount (\u20a62,000) >
    # grand_total (\u20a61,980) and books the \u20a620 surplus as change owed to
    # the customer (Cash Sales [outlet] Cr 20 + Trade Receivables Dr 20).
    # The rounding_adjustment we set above ALREADY books the \u20a620 to the
    # Round Off Expense account; treating it again as change would
    # double-count and leave a phantom \u20a620 outstanding (=> "Partly Paid").
    if hasattr(doc, "change_amount"):
        doc.change_amount = 0
    if hasattr(doc, "base_change_amount"):
        doc.base_change_amount = 0
    if hasattr(doc, "write_off_amount"):
        # Only suppress write_off when it was implicitly added by Frappe's
        # surplus-payment handling (i.e. equals our total_overage). A
        # cashier-typed write_off should be respected.
        if abs(flt(doc.write_off_amount) - total_overage) < TOLERANCE:
            doc.write_off_amount = 0
            if hasattr(doc, "base_write_off_amount"):
                doc.base_write_off_amount = 0
