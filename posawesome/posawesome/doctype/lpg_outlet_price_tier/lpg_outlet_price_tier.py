# Copyright (c) 2026, Sungas — POS Awesome customization
# For license information, see license.txt

import frappe
from frappe.model.document import Document
from frappe import _


class LPGOutletPriceTier(Document):
    def validate(self):
        self._validate_qty_range()
        self._validate_date_range()
        if self.enabled:
            from posawesome.posawesome.api.lpg_pricing_guards import assert_not_below_cost
            assert_not_below_cost(self.item_code, self.rate)

    def on_update(self):
        from posawesome.posawesome.api.lpg_pricing_guards import sync_national_item_price
        sync_national_item_price(self)

    def _validate_qty_range(self):
        if self.min_qty and self.max_qty and self.max_qty > 0 and self.min_qty > self.max_qty:
            frappe.throw(_("Min Qty cannot exceed Max Qty."))
        if self.min_qty and self.min_qty < 0:
            frappe.throw(_("Min Qty cannot be negative."))
        if self.max_qty and self.max_qty < 0:
            frappe.throw(_("Max Qty cannot be negative."))

    def _validate_date_range(self):
        if self.valid_from and self.valid_to and self.valid_to < self.valid_from:
            frappe.throw(_("Valid To cannot be before Valid From."))
