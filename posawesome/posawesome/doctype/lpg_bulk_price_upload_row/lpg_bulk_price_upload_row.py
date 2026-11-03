# Copyright (c) 2026, Sungas — POS Awesome customization
# For license information, see license.txt
"""Child table for `LPG Bulk Price Upload`. No business logic lives here —
all validation runs on the parent doc so we can short-circuit on
parse failures and keep the CSV path testable as a pure function.
"""

from frappe.model.document import Document


class LPGBulkPriceUploadRow(Document):
    pass
