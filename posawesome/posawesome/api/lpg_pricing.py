"""
LPG tiered-pricing engine.

Resolves the most-specific applicable `LPG Outlet Price Tier` for each item
row of Sales Invoice / POS Invoice / Quotation / Sales Order, replacing
native Frappe Pricing Rules (which can't combine Customer Group + Territory
without conflict in v15).

Lookup priority (most-specific wins):
    1. Exact (customer_group, territory) match
    2. Tiers where qty falls within [min_qty, max_qty]   (0 = no bound)
    3. Tiers active on posting_date (valid_from..valid_to)
    4. enabled = 1

If multiple tiers match, the one with the highest min_qty wins
(largest volume bracket = most-specific bulk pricing).
"""

from __future__ import annotations

import frappe
from frappe.utils import flt, getdate, today


def _get_customer_meta(customer: str) -> dict:
    if not customer:
        return {}
    row = frappe.db.get_value(
        "Customer",
        customer,
        ["customer_group", "territory"],
        as_dict=True,
    )
    return row or {}


def _get_pos_profile_territory(pos_profile: str | None) -> str | None:
    """Return the territory configured on a POS Profile, or None."""
    if not pos_profile:
        return None
    return frappe.db.get_value("POS Profile", pos_profile, "territory") or None


def find_applicable_tier(
    item_code: str,
    customer_group: str | None,
    territory: str | None,
    qty: float,
    posting_date: str | None = None,
) -> dict | None:
    """
    Return the best-matching tier dict (or None).

    Phase-5 Sungas business rule:
        The `territory` argument should be the OUTLET / POS-Profile territory,
        NOT the customer's registered territory. (Where the cylinder is filled
        determines the price, not where the customer lives.)

    Lookup precedence:
        1. Exact (item_code, customer_group, outlet_territory) match.
        2. Fall back to (item_code, customer_group) — any territory — to cover
           customer groups that haven't been priced at every outlet yet.
    """
    if not item_code or not customer_group:
        return None

    posting_date = posting_date or today()
    qty = flt(qty or 0)
    pd = getdate(posting_date)

    def _matches(t: dict) -> bool:
        mn = flt(t.get("min_qty") or 0)
        mx = flt(t.get("max_qty") or 0)
        if qty < mn:
            return False
        if mx > 0 and qty > mx:
            return False
        if t.get("valid_from") and getdate(t["valid_from"]) > pd:
            return False
        if t.get("valid_to") and getdate(t["valid_to"]) < pd:
            return False
        return True

    def _best(rows: list) -> dict | None:
        matched = [t for t in rows if _matches(t)]
        if not matched:
            return None
        matched.sort(
            key=lambda t: (flt(t.get("min_qty") or 0), str(t.get("valid_from") or "")),
            reverse=True,
        )
        return matched[0]

    fields = [
        "name", "rate", "currency", "min_qty", "max_qty",
        "valid_from", "valid_to", "territory",
    ]

    # 1. Tier scoped to the outlet's territory.
    if territory:
        scoped = frappe.get_all(
            "LPG Outlet Price Tier",
            filters={
                "item_code": item_code,
                "customer_group": customer_group,
                "territory": territory,
                "enabled": 1,
            },
            fields=fields,
        )
        best = _best(scoped)
        if best:
            return best

    # 2. Fall back to customer_group only (any territory). For tiers configured
    # with an empty territory, OR for outlets that haven't been priced yet.
    any_terr = frappe.get_all(
        "LPG Outlet Price Tier",
        filters={
            "item_code": item_code,
            "customer_group": customer_group,
            "enabled": 1,
        },
        fields=fields,
    )
    return _best(any_terr)


def apply_tiered_pricing(doc, method=None):
    """
    Document-level entry. Iterates rows of doc.items and overrides `rate`
    whenever a tier matches.

    Uses the OUTLET territory (Sales Invoice.pos_profile.territory), not the
    customer's registered territory. See find_applicable_tier docstring.
    """
    if not getattr(doc, "items", None):
        return

    meta = _get_customer_meta(getattr(doc, "customer", None))
    customer_group = meta.get("customer_group")
    if not customer_group:
        return

    outlet_territory = _get_pos_profile_territory(getattr(doc, "pos_profile", None))
    posting_date = getattr(doc, "posting_date", None) or getattr(doc, "transaction_date", None)

    any_rate_changed = False

    for row in doc.items:
        tier = find_applicable_tier(
            item_code=row.item_code,
            customer_group=customer_group,
            territory=outlet_territory,
            qty=flt(getattr(row, "qty", 0) or 0),
            posting_date=posting_date,
        )
        if not tier:
            continue

        tier_rate = flt(tier["rate"])
        if tier_rate <= 0:
            continue

        if flt(getattr(row, "rate", 0)) != tier_rate:
            row.price_list_rate = tier_rate
            row.rate = tier_rate
            any_rate_changed = True
            if hasattr(row, "posa_offers"):
                existing = row.posa_offers or ""
                marker = f"LPG-Tier:{tier['name']}"
                if marker not in existing:
                    row.posa_offers = (existing + "," + marker).strip(",")

    if any_rate_changed and hasattr(doc, "calculate_taxes_and_totals"):
        doc.calculate_taxes_and_totals()


@frappe.whitelist()
def get_tier_rate(item_code: str, customer: str, qty: float = 0,
                  posting_date: str = None, pos_profile: str = None) -> dict:
    """
    Lightweight API used by POS Awesome to fetch the tier rate before
    submitting an invoice.

    `pos_profile` (optional) determines the outlet territory; if omitted,
    falls back to customer-group-only lookup.
    """
    meta = _get_customer_meta(customer)
    outlet_territory = _get_pos_profile_territory(pos_profile)
    tier = find_applicable_tier(
        item_code=item_code,
        customer_group=meta.get("customer_group"),
        territory=outlet_territory,
        qty=flt(qty),
        posting_date=posting_date,
    )
    if not tier:
        return {"has_tier": False}
    return {
        "has_tier": True,
        "tier_name": tier["name"],
        "rate": flt(tier["rate"]),
        "currency": tier["currency"],
        "min_qty": flt(tier.get("min_qty") or 0),
        "max_qty": flt(tier.get("max_qty") or 0),
        "matched_territory": tier.get("territory"),
    }


@frappe.whitelist()
def get_tier_rates_bulk(items, customer: str,
                        posting_date: str = None, pos_profile: str = None) -> dict:
    """
    Batched variant. POS Awesome calls this once whenever the customer changes
    or a new item is added.

    Args:
        items: list[dict] with keys {item_code, qty}. Accepts a JSON string too.
        customer: customer name.
        posting_date: optional ISO date.
        pos_profile: POS Profile name — used to derive the OUTLET territory.

    Returns:
        {
            "customer_group": <str>,
            "outlet_territory": <str>,
            "rows": [...],
            "all_have_tier": <bool>
        }
    """
    import json
    if isinstance(items, str):
        try:
            items = json.loads(items)
        except Exception:
            items = []
    if not isinstance(items, list):
        items = []

    meta = _get_customer_meta(customer) if customer else {}
    outlet_territory = _get_pos_profile_territory(pos_profile)
    customer_group = meta.get("customer_group")

    rows = []
    all_have_tier = True
    for row in items:
        if not isinstance(row, dict):
            continue
        item_code = row.get("item_code")
        if not item_code:
            continue
        tier = find_applicable_tier(
            item_code=item_code,
            customer_group=customer_group,
            territory=outlet_territory,
            qty=flt(row.get("qty") or 0),
            posting_date=posting_date,
        )
        if tier:
            rows.append({
                "item_code": item_code,
                "qty": flt(row.get("qty") or 0),
                "has_tier": True,
                "tier_name": tier["name"],
                "rate": flt(tier["rate"]),
                "currency": tier["currency"],
                "min_qty": flt(tier.get("min_qty") or 0),
                "max_qty": flt(tier.get("max_qty") or 0),
                "matched_territory": tier.get("territory"),
            })
        else:
            all_have_tier = False
            rows.append({
                "item_code": item_code,
                "qty": flt(row.get("qty") or 0),
                "has_tier": False,
            })
    return {
        "customer": customer,
        "customer_group": customer_group,
        "outlet_territory": outlet_territory,
        "rows": rows,
        "all_have_tier": all_have_tier,
    }

