# Copyright (c) 2026, Sungas — POS Awesome customization
# For license information, see license.txt
"""LPG Market Price Snapshot (Pricing Wave D — P-8).

A submittable point-in-time observation of an LPG product's market
price. Captured by Plant Managers (competitor visits / NNPC pump
boards) or Head of Sales (vendor quotes, government circulars).

Used by the P-9 Margin Band cron and P-11 KPI reports.
"""

from __future__ import annotations

import frappe
from frappe.model.document import Document
from frappe.utils import now


class LPGMarketPriceSnapshot(Document):
    def validate(self):
        if not self.captured_by:
            self.captured_by = frappe.session.user
        if not self.capture_datetime:
            self.capture_datetime = now()
