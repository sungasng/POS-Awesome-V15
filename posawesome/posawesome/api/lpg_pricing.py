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


ALL_GROUPS = "All Customer Groups"


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
    """
    Return the OUTLET territory for a POS Profile.

    POS Profile in ERPNext v15 has no direct `territory` column — outlet
    locality is encoded in the warehouse instead (e.g. `Pedro - SCL`).
    We derive the Territory by reading the warehouse's `warehouse_name`
    (the bit before ' - <abbr>') and checking that a Territory exists
    with the same name.
    """
    if not pos_profile:
        return None
    warehouse = frappe.db.get_value("POS Profile", pos_profile, "warehouse")
    if not warehouse:
        return None
    wh_name = frappe.db.get_value("Warehouse", warehouse, "warehouse_name") or ""
    if wh_name and frappe.db.exists("Territory", wh_name):
        return wh_name
    return None


def _walk_up_territory_chain(territory: str | None, max_hops: int = 8) -> list[str]:
    """
    Return [outlet_leaf, parent, grandparent, ..., root] for the Territory
    tree starting at `territory`. Caps at `max_hops` to defend against
    accidental cycles in user-edited trees.

    Pricing Wave A — P-1 ("Regional Base + Plant Override"): the resolver
    must try the outlet leaf first, then progressively wider parents
    (Region, then Nigeria), so that a regional base price covers every
    plant that does not carry an explicit override row.
    """
    chain: list[str] = []
    seen: set[str] = set()
    cur = territory
    hops = 0
    while cur and cur not in seen and hops < max_hops:
        chain.append(cur)
        seen.add(cur)
        parent = frappe.db.get_value("Territory", cur, "parent_territory")
        if not parent or parent == cur:
            break
        cur = parent
        hops += 1
    return chain


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
        The `territory` argument is the OUTLET / POS-Profile territory,
        NOT the customer's registered territory. (Where the cylinder is filled
        determines the price, not where the customer lives.)

    Pricing Wave A — P-1 ("Regional Base + Plant Override"):
        Lookup precedence (first hit wins):
            1. Exact tier on the outlet leaf territory          (Plant Override)
            2. Walk up parent_territory chain                   (Regional Base)
            3. National row (territory = empty / blank)         (legacy safety valve)

        Backward-compatible with the 64 production rows (all seeded with a
        leaf territory), because levels 2 and 3 only fire when level 1 finds
        nothing. Operationally this means: drop a single row at Region level
        and every plant under it inherits the price unless overridden.

        Cross-sibling fallback remains DISABLED. Pedro never silently picks
        up Ekehuan's price unless both plants share a common parent that
        carries an explicit Regional Base row.
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

    # Patch 0017: a row for the customer's own group wins; otherwise a row
    # for "All Customer Groups" (one price for every customer type) applies.
    groups = [customer_group] + ([ALL_GROUPS] if customer_group != ALL_GROUPS else [])

    # 1+2. Walk the territory chain from outlet leaf up to the root.
    #      First level that has a matching row wins.
    for level in _walk_up_territory_chain(territory):
        for grp in groups:
            scoped = frappe.get_all(
                "LPG Outlet Price Tier",
                filters={
                    "item_code": item_code,
                    "customer_group": grp,
                    "territory": level,
                    "enabled": 1,
                },
                fields=fields,
            )
            best = _best(scoped)
            if best:
                return best

    # 3. Optional "global / any-outlet" tier: rows with NO territory set.
    #    Safety valve for SKUs priced uniformly nationwide without a
    #    Territory tree edit. Production has none of these today.
    for grp in groups:
        global_rows = frappe.get_all(
            "LPG Outlet Price Tier",
            filters={
                "item_code": item_code,
                "customer_group": grp,
                "enabled": 1,
            },
            or_filters=[
                ["territory", "is", "not set"],
                ["territory", "=", ""],
            ],
            fields=fields,
        )
        best = _best(global_rows)
        if best:
            return best
    return None


def _policy_enabled() -> bool:
    """
    Read `Sungas Pricing Policy.policy_enabled` once. When the policy doctype
    isn't installed (e.g., fresh local dev) we default to enabled so the
    pricing guard never silently disappears in production.
    """
    try:
        if not frappe.db.exists("DocType", "Sungas Pricing Policy"):
            return True
        val = frappe.db.get_single_value("Sungas Pricing Policy", "policy_enabled")
        return bool(val) if val is not None else True
    except Exception:
        return True


# Customer groups for which a non-zero rate is mandatory at save time
# (Pricing Wave A — P-4 hard zero-price block). Hard-coded by design: these
# are the LPG-style sales channels Section 1 governs. Other groups (e.g.
# 'Internal Transfer', 'Inter-Branch') legitimately move stock at 0.
_LPG_PRICED_GROUPS = {"Retail", "Bulk", "Industrial", "Wholesale", "Commercial"}


def apply_tiered_pricing(doc, method=None):
    """
    Document-level entry. Iterates rows of doc.items and overrides `rate`
    whenever a tier matches.

    Uses the OUTLET territory (derived from Sales Invoice.pos_profile.warehouse),
    not the customer's registered territory. See find_applicable_tier docstring.

    Phase-5 Sungas business rule: for any item that has at least one
    LPG Outlet Price Tier row configured (i.e., a 'tiered item'), the sale
    MUST resolve to a matching tier. If no tier matches the
    (customer_group, outlet_territory, qty, posting_date) combination, the
    save is rejected with a clear message. Items that have NO tier rows at
    all (accessories, cylinders, cookers) fall through to the normal price
    list rate.

    Pricing Wave A — P-4 ("Hard zero-price block at POS"):
        After tier resolution, any row whose final `rate <= 0` causes the
        save to fail when the customer belongs to an LPG-priced group
        (Retail / Bulk / Industrial / Wholesale / Commercial). This closes
        the loophole where a non-tiered SKU (cylinder, regulator) slipped
        through with a missing standard Item Price.

    The whole guard short-circuits cleanly when
    `Sungas Pricing Policy.policy_enabled` is unchecked.
    """
    if not getattr(doc, "items", None):
        return
    if not _policy_enabled():
        return

    meta = _get_customer_meta(getattr(doc, "customer", None))
    customer_group = meta.get("customer_group")

    outlet_territory = _get_pos_profile_territory(getattr(doc, "pos_profile", None))
    posting_date = getattr(doc, "posting_date", None) or getattr(doc, "transaction_date", None)

    any_rate_changed = False
    missing: list[tuple[str, str]] = []  # (item_code, reason)
    zero_rate_rows: list[tuple[str, float]] = []  # (item_code, rate)

    for row in doc.items:
        # Does this item have ANY tier rows configured? If not, it's a
        # non-tiered item (accessory/cylinder) — leave it on price-list rate.
        has_any_tier = frappe.db.exists(
            "LPG Outlet Price Tier",
            {"item_code": row.item_code, "enabled": 1},
        )

        if has_any_tier:
            # Tiered item: customer_group is mandatory.
            if not customer_group:
                missing.append((row.item_code, "no customer / customer_group"))
                continue

            # Sungas posa-0030: tiers are per stock unit (kg). A "50kg Cyl" line is priced
            # 50 x the kg rate and its quantity band is judged in kg (qty x size).
            cf = flt(getattr(row, "conversion_factor", 0) or 0) or 1
            tier = find_applicable_tier(
                item_code=row.item_code,
                customer_group=customer_group,
                territory=outlet_territory,
                qty=flt(getattr(row, "qty", 0) or 0) * cf,
                posting_date=posting_date,
            )
            if not tier:
                missing.append((
                    row.item_code,
                    f"no tier for (customer_group={customer_group!r}, "
                    f"territory={outlet_territory!r})",
                ))
                continue

            tier_rate = flt(tier["rate"])
            if tier_rate <= 0:
                missing.append((row.item_code, f"tier {tier['name']} has rate=0"))
                continue
            tier_rate = flt(tier_rate * cf, 2)

            if flt(getattr(row, "rate", 0)) != tier_rate:
                row.price_list_rate = tier_rate
                row.rate = tier_rate
                any_rate_changed = True
                if hasattr(row, "posa_offers"):
                    existing = row.posa_offers or ""
                    marker = f"LPG-Tier:{tier['name']}"
                    if marker not in existing:
                        row.posa_offers = (existing + "," + marker).strip(",")

        # P-4: regardless of tiered-ness, refuse a zero rate for LPG-priced
        # customer groups. This catches the case where a non-tiered SKU
        # (e.g. cylinder) has no Item Price defined and would otherwise
        # submit at 0.
        if customer_group in _LPG_PRICED_GROUPS and flt(getattr(row, "rate", 0)) <= 0:
            zero_rate_rows.append((row.item_code, flt(getattr(row, "rate", 0))))

    if missing:
        lines = "\n".join(f"  - {ic}: {reason}" for ic, reason in missing)
        frappe.throw(
            (
                "LPG tier pricing required but no matching tier was found "
                "for the following item(s):\n{0}\n\n"
                "Configure an 'LPG Outlet Price Tier' row, or pick a "
                "customer / outlet whose group + territory has a price."
            ).format(lines),
            title="No LPG Tier Price",
        )

    if zero_rate_rows:
        lines = "\n".join(f"  - {ic}: rate={r}" for ic, r in zero_rate_rows)
        frappe.throw(
            (
                "Zero-price items are blocked for {grp} customers under "
                "Pricing Wave A (P-4). Set a non-zero price (LPG Outlet "
                "Price Tier for governed SKUs, or a standard Item Price "
                "for accessories) before submitting:\n{lines}"
            ).format(grp=customer_group, lines=lines),
            title="Zero Price Blocked",
        )

    if any_rate_changed and hasattr(doc, "calculate_taxes_and_totals"):
        doc.calculate_taxes_and_totals()


def override_item_detail_with_tier(item_detail: dict, customer: str | None,
                                    pos_profile: str | None,
                                    posting_date: str | None = None) -> dict:
    """
    Mutate a single get_item_detail / build_details response dict so its
    `rate` / `price_list_rate` reflect the LPG Outlet Price Tier for
    (customer's group, pos_profile's outlet territory).

    Called by `get_item_detail` and `get_items_details` in api/items.py so
    that every POS Awesome refresh returns the already-tiered rate. Without
    this hook, POS Awesome's background `refreshAllItemDetailsInBatches`
    would overwrite our front-end tier rate with the price-list rate.

    Sungas Phase-5: when no customer is selected yet, fall back to the
    outlet's RETAIL tier rate so the item card already shows the right
    default for that branch (e.g. \u20a61,365 at Asaba, \u20a61,380 at Eleme).
    """
    if not item_detail:
        return item_detail
    item_code = item_detail.get("item_code") or item_detail.get("name")
    if not item_code:
        return item_detail

    if customer:
        meta = _get_customer_meta(customer)
        customer_group = meta.get("customer_group")
    else:
        customer_group = "Retail"  # default for the item-card display
    if not customer_group:
        return item_detail

    outlet_territory = _get_pos_profile_territory(pos_profile)
    # Sungas posa-0023: tiers are per kg; a cylinder unit (e.g. "50kg Cyl") = kg rate x size.
    cf = flt(item_detail.get("conversion_factor") or 1) or 1
    qty = flt(item_detail.get("qty") or 1) * cf

    tier = find_applicable_tier(
        item_code=item_code,
        customer_group=customer_group,
        territory=outlet_territory,
        qty=qty,
        posting_date=posting_date,
    )
    if not tier:
        return item_detail

    tier_rate = flt(tier.get("rate") or 0)
    if tier_rate <= 0:
        return item_detail

    tier_rate = flt(tier_rate * cf, 2)
    # Stamp the tier rate on every field POS Awesome reads.
    item_detail["rate"] = tier_rate
    item_detail["price_list_rate"] = tier_rate
    item_detail["base_rate"] = tier_rate
    item_detail["base_price_list_rate"] = tier_rate
    item_detail["lpg_tier_applied"] = tier.get("name")
    item_detail["lpg_tier_rate"] = tier_rate
    return item_detail


def apply_tiers_to_rows(rows: list, customer: str | None, pos_profile: str | None,
                         posting_date: str | None = None) -> list:
    """Bulk variant of override_item_detail_with_tier for `build_details`.

    Sungas Phase-5: when customer is None, defaults to the outlet's RETAIL
    tier rate so the item-grid display shows the outlet-specific Retail
    price before any customer is picked.
    """
    if not rows:
        return rows
    if customer:
        meta = _get_customer_meta(customer)
        customer_group = meta.get("customer_group")
    else:
        customer_group = "Retail"
    if not customer_group:
        return rows
    outlet_territory = _get_pos_profile_territory(pos_profile)

    for row in rows:
        if not isinstance(row, dict):
            continue
        item_code = row.get("item_code") or row.get("name")
        if not item_code:
            continue
        tier = find_applicable_tier(
            item_code=item_code,
            customer_group=customer_group,
            territory=outlet_territory,
            qty=flt(row.get("qty") or 1),
            posting_date=posting_date,
        )
        if not tier:
            continue
        tier_rate = flt(tier.get("rate") or 0)
        if tier_rate <= 0:
            continue
        row["rate"] = tier_rate
        row["price_list_rate"] = tier_rate
        row["base_rate"] = tier_rate
        row["base_price_list_rate"] = tier_rate
        row["lpg_tier_applied"] = tier.get("name")
        row["lpg_tier_rate"] = tier_rate
    return rows


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
        # Sungas Phase-5: only flag a missing tier when this item is a
        # 'tiered item' (has at least one LPG Outlet Price Tier row).
        # Non-tiered items (cylinders, regulators, cookers, accessories)
        # legitimately have no tier and should NOT trigger the
        # "no tier rate for this customer" toast.
        is_tiered_item = bool(frappe.db.exists(
            "LPG Outlet Price Tier",
            {"item_code": item_code, "enabled": 1},
        ))
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
                "is_tiered_item": is_tiered_item,
                "has_tier": True,
                "tier_name": tier["name"],
                "rate": flt(tier["rate"]),
                "currency": tier["currency"],
                "min_qty": flt(tier.get("min_qty") or 0),
                "max_qty": flt(tier.get("max_qty") or 0),
                "matched_territory": tier.get("territory"),
            })
        else:
            # Only flag the "all_have_tier=False" alarm when the item is
            # actually tiered. Non-tiered items don't break the alarm.
            if is_tiered_item:
                all_have_tier = False
            rows.append({
                "item_code": item_code,
                "qty": flt(row.get("qty") or 0),
                "is_tiered_item": is_tiered_item,
                "has_tier": False,
            })
    return {
        "customer": customer,
        "customer_group": customer_group,
        "outlet_territory": outlet_territory,
        "rows": rows,
        "all_have_tier": all_have_tier,
    }

