# Copyright (c) 2026, Sungas — POS Awesome customization
"""Script Report — LPG Tier Resolver Diagnostic.

Lets Head of Sales / Head of Finance / Plant Manager simulate exactly
what `find_applicable_tier` would return for a given combination of
inputs, without console access. The output shows the **walk-up chain
explicitly** so the user can see which territory level resolved (or
why no tier was found).

Filter inputs (all optional except `item_code`):
    - item_code            (Item link, REQUIRED)
    - customer_group       (Customer Group link, REQUIRED)
    - territory            (Territory link — outlet leaf for realism)
    - qty                  (Float, default 1)
    - posting_date         (Date, default today)

Output rows: one per level walked, with a status column indicating the
winning level + the matched tier (if any).
"""

from __future__ import annotations

import frappe  # type: ignore
from frappe import _
from frappe.utils import flt, today

from posawesome.posawesome.api.lpg_pricing import (
    _walk_up_territory_chain,
    find_applicable_tier,
)


def execute(filters: dict | None = None):
    filters = filters or {}
    item_code = (filters.get("item_code") or "").strip()
    customer_group = (filters.get("customer_group") or "").strip()
    territory = (filters.get("territory") or "").strip() or None
    qty = flt(filters.get("qty") or 1)
    posting_date = filters.get("posting_date") or today()

    if not item_code or not customer_group:
        frappe.throw(_("Item and Customer Group are required."))

    columns = [
        {"label": "Level", "fieldname": "level", "fieldtype": "Int", "width": 70},
        {"label": "Territory Scope", "fieldname": "scope", "fieldtype": "Link", "options": "Territory", "width": 220},
        {"label": "Matching Tier", "fieldname": "tier_name", "fieldtype": "Link", "options": "LPG Outlet Price Tier", "width": 220},
        {"label": "Rate", "fieldname": "rate", "fieldtype": "Currency", "width": 130},
        {"label": "Qty Window", "fieldname": "qty_window", "fieldtype": "Data", "width": 130},
        {"label": "Valid Window", "fieldname": "valid_window", "fieldtype": "Data", "width": 160},
        {"label": "Winner", "fieldname": "winner", "fieldtype": "Data", "width": 90},
    ]

    # Resolve once via the production resolver so we know who wins.
    winning = find_applicable_tier(
        item_code=item_code,
        customer_group=customer_group,
        territory=territory,
        qty=qty,
        posting_date=posting_date,
    )

    rows: list[list] = []
    chain = _walk_up_territory_chain(territory)
    if not chain:
        # Caller asked for an unbound (no-territory) lookup — show only
        # the global safety-valve outcome.
        chain = ["(no territory)"]

    seen_winner = False
    for idx, level in enumerate(chain, start=1):
        scope = None if level == "(no territory)" else level
        rows_at_level = frappe.get_all(
            "LPG Outlet Price Tier",
            filters={
                "item_code": item_code,
                "customer_group": customer_group,
                "territory": scope,
                "enabled": 1,
            } if scope else {
                "item_code": item_code,
                "customer_group": customer_group,
                "enabled": 1,
            },
            fields=["name", "rate", "min_qty", "max_qty", "valid_from", "valid_to"],
        )
        if not rows_at_level:
            rows.append([
                idx, level, "(no tier at this level)", 0,
                "—", "—", "",
            ])
            continue
        for r in rows_at_level:
            is_winner = winning and r["name"] == winning.get("name") and not seen_winner
            rows.append([
                idx,
                level,
                r["name"],
                r["rate"],
                _qty_window(r),
                _valid_window(r),
                "★ WINNER" if is_winner else "",
            ])
            if is_winner:
                seen_winner = True

    # Add a summary row if there is no winner at all.
    if not winning:
        rows.append([
            len(chain) + 1,
            "(global / empty-territory)",
            "(no tier resolved — POS would block this sale)",
            0, "—", "—", "✘ NO MATCH",
        ])

    return columns, rows


def _qty_window(r: dict) -> str:
    mn = flt(r.get("min_qty") or 0)
    mx = flt(r.get("max_qty") or 0)
    return f"{mn:g} – {('∞' if mx == 0 else f'{mx:g}')}"


def _valid_window(r: dict) -> str:
    vf = r.get("valid_from") or "open"
    vt = r.get("valid_to") or "open"
    return f"{vf} → {vt}"
