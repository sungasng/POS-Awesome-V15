"""Patch 0017 -- pricing guards shared by PCR, Bulk Upload and the tier itself.

* Below-cost block (IAS 2 NRV): a selling price below the item's current unit
  cost is refused. Pathway: Finance writes the stock down to net realisable
  value (valuation-only Stock Reconciliation); the unit cost then drops and
  the price passes.
* National price sync: an enabled national tier (All Customer Groups, no
  plant/region, no qty band) also updates the default selling price list.
"""
from __future__ import annotations

import frappe
from frappe.utils import flt

ALL_GROUPS = "All Customer Groups"
NATIONAL_TERRITORIES = ("", "Nigeria", "All Territories")


def item_unit_cost(item_code: str):
    """Weighted-average unit cost across warehouses; None when never stocked/bought."""
    bins = frappe.get_all("Bin", filters={"item_code": item_code, "actual_qty": [">", 0]},
                          fields=["actual_qty", "stock_value"])
    qty = sum(flt(b["actual_qty"]) for b in bins)
    if qty > 0:
        return flt(sum(flt(b["stock_value"]) for b in bins) / qty, 2)
    for field in ("valuation_rate", "last_purchase_rate"):
        v = flt(frappe.db.get_value("Item", item_code, field))
        if v > 0:
            return v
    return None


def below_cost_message(item_code: str, rate) -> str | None:
    cost = item_unit_cost(item_code)
    if cost is None or flt(rate) >= cost:
        return None
    return (
        f"{item_code}: proposed price NGN {flt(rate):,.2f} is below unit cost NGN {cost:,.2f} "
        f"(gap NGN {cost - flt(rate):,.2f}). To sell at this price, Finance must first write the "
        "stock down to net realisable value (Stock Reconciliation, valuation only, approved by "
        "Head of Finance); the price can then be approved."
    )


def assert_not_below_cost(item_code: str, rate) -> None:
    msg = below_cost_message(item_code, rate)
    if msg:
        frappe.throw(msg, title="Below Cost Price")


def is_national(tier) -> bool:
    return (
        tier.get("customer_group") == ALL_GROUPS
        and (tier.get("territory") or "") in NATIONAL_TERRITORIES
        and not flt(tier.get("min_qty"))
        and not flt(tier.get("max_qty"))
    )


def sync_national_item_price(tier) -> None:
    if not tier.get("enabled") or not is_national(tier):
        return
    price_list = frappe.db.get_single_value("Selling Settings", "selling_price_list") or "SCL Standard Selling"
    name = frappe.db.get_value("Item Price", {"item_code": tier.item_code, "price_list": price_list,
                                              "customer": ["is", "not set"]}, "name")
    if name:
        if flt(frappe.db.get_value("Item Price", name, "price_list_rate")) != flt(tier.rate):
            frappe.db.set_value("Item Price", name, "price_list_rate", tier.rate)
        return
    frappe.get_doc({"doctype": "Item Price", "item_code": tier.item_code, "price_list": price_list,
                    "price_list_rate": tier.rate, "selling": 1}).insert(ignore_permissions=True)
