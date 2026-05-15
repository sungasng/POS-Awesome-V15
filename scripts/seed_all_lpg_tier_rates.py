"""
Phase 5 — Seed the full LPG Outlet Price Tier matrix from the customer's
official price list (Pricelist.xlsx, 2026-02 revision).

Matrix sourced from the spreadsheet's 'LPG' sheet:

  Region / Outlets             Retail Commercial Distributor Bulk
  OGUN 1   (Maba/Sefu/Ebutte/Aseese)             1350 1300 1160 -
  OGUN 2   (Itele/Iju-Ota/Osi-Ota/Ijoko)         1350 1300 1150 -
  LAGOS 1  (Ikeja/Oworo/Pedro/Bolade/Mafoluku)   1360 1300 1140 -
  RIVERS 1 (Eleme/Reclamation)                   1380 1350 1180 -
  EDO 1    (Ekehuan/Upper Mission/Idowina/Idokpa/Okhuoromi)
                                                 1320 1305 1170 - (Ekehuan also has Bulk 1200)
  DELTA 1  (Asaba)                               1365 1365 1180 -

Behaviour:
  - Diagnoses available Customer Groups + Territories first; prints what
    exists and how each maps to the spreadsheet headers.
  - For every (LPG-REFILL, customer_group, territory) combo with a price in
    the spreadsheet, idempotently UPSERTs an 'LPG Outlet Price Tier' row.
  - PROTECTED: (LPG-REFILL, Retail, Pedro) at NGN 3,000 — left untouched so
    the team can keep visually validating the tier engine vs the
    Lagos-Retail default of NGN 1,360. To bring Pedro Retail to production
    (NGN 1,360), edit PROTECT_PEDRO_RETAIL_TEST = False below and re-run.
  - Skip & WARN for unknown customer groups or missing territories.
  - Commits + clears cache.

Run on bench:
  bench --site sungasmis.v.frappe.cloud execute \
    "exec(open('/tmp/seed_all_lpg_tier_rates.py').read())"
"""

from __future__ import annotations

import sys
from typing import Optional

import frappe


# -----------------------------------------------------------------------------
# CONFIG
# -----------------------------------------------------------------------------
ITEM_CODE = "LPG-REFILL"
CURRENCY = "NGN"

# If True, the existing test row (LPG-REFILL, Retail, Pedro) = 3,000 is left
# alone (per user's 2b decision). Flip to False once the team is done testing
# and you want production prices everywhere.
PROTECT_PEDRO_RETAIL_TEST = True

# Spreadsheet headers -> aliases to try when matching ERPNext Customer Groups.
# The first alias that exists in 'Customer Group' wins. Case-insensitive.
CUSTOMER_GROUP_ALIASES: dict[str, list[str]] = {
    "Retail":       ["Retail", "Retailer", "Retail Customer"],
    "Commercial":   ["Commercial", "Commercial Customer"],
    "Distributor":  ["Distributor", "Distributors", "Wholesale", "Wholesaler"],
    "Bulk":         ["Bulk", "Bulk ex-depot", "Bulk Ex-Depot", "Industrial", "Bulk Customer"],
}

# Territory aliases per outlet — first matching existing Territory wins.
TERRITORY_ALIASES: dict[str, list[str]] = {
    "Maba":          ["Maba"],
    "Sefu":          ["Sefu"],
    "Ebutte":        ["Ebutte", "Ebute"],
    "Aseese":        ["Aseese", "Asese"],
    "Itele":         ["Itele"],
    "Iju-Ota":       ["Iju-Ota", "Iju Ota", "Ijuota"],
    "Osi-Ota":       ["Osi-Ota", "Osi Ota", "Osiota"],
    "Ijoko":         ["Ijoko"],
    "Ikeja":         ["Ikeja"],
    "Oworo":         ["Oworo"],
    "Pedro":         ["Pedro"],
    "Bolade":        ["Bolade"],
    "Mafoluku":      ["Mafoluku"],
    "Eleme":         ["Eleme"],
    "Reclamation":   ["Reclamation"],
    "Ekehuan":       ["Ekehuan"],
    "Upper Mission": ["Upper Mission", "Upper-Mission", "UpperMission"],
    "Idowina":       ["Idowina"],
    "Idokpa":        ["Idokpa"],
    "Okhuoromi":     ["Okhuoromi"],
    "Asaba":         ["Asaba"],
}

# Price matrix: outlet -> {customer_group: rate}
# Bulk is only present where the spreadsheet explicitly listed a price.
MATRIX: dict[str, dict[str, int]] = {
    # OGUN 1
    "Maba":          {"Retail": 1350, "Commercial": 1300, "Distributor": 1160},
    "Sefu":          {"Retail": 1350, "Commercial": 1300, "Distributor": 1160},
    "Ebutte":        {"Retail": 1350, "Commercial": 1300, "Distributor": 1160},
    "Aseese":        {"Retail": 1350, "Commercial": 1300, "Distributor": 1160},
    # OGUN 2
    "Itele":         {"Retail": 1350, "Commercial": 1300, "Distributor": 1150},
    "Iju-Ota":       {"Retail": 1350, "Commercial": 1300, "Distributor": 1150},
    "Osi-Ota":       {"Retail": 1350, "Commercial": 1300, "Distributor": 1150},
    "Ijoko":         {"Retail": 1350, "Commercial": 1300, "Distributor": 1150},
    # LAGOS 1
    "Ikeja":         {"Retail": 1360, "Commercial": 1300, "Distributor": 1140},
    "Oworo":         {"Retail": 1360, "Commercial": 1300, "Distributor": 1140},
    "Pedro":         {"Retail": 1360, "Commercial": 1300, "Distributor": 1140},
    "Bolade":        {"Retail": 1360, "Commercial": 1300, "Distributor": 1140},
    "Mafoluku":      {"Retail": 1360, "Commercial": 1300, "Distributor": 1140},
    # RIVERS 1
    "Eleme":         {"Retail": 1380, "Commercial": 1350, "Distributor": 1180},
    "Reclamation":   {"Retail": 1380, "Commercial": 1350, "Distributor": 1180},
    # EDO 1
    "Ekehuan":       {"Retail": 1320, "Commercial": 1305, "Distributor": 1170, "Bulk": 1200},
    "Upper Mission": {"Retail": 1320, "Commercial": 1305, "Distributor": 1170},
    "Idowina":       {"Retail": 1320, "Commercial": 1305, "Distributor": 1170},
    "Idokpa":        {"Retail": 1320, "Commercial": 1305, "Distributor": 1170},
    "Okhuoromi":     {"Retail": 1320, "Commercial": 1305, "Distributor": 1170},
    # DELTA 1
    "Asaba":         {"Retail": 1365, "Commercial": 1365, "Distributor": 1180},
}


# -----------------------------------------------------------------------------
# HELPERS
# -----------------------------------------------------------------------------
def _resolve_customer_group(header: str) -> Optional[str]:
    """Return an existing Customer Group name matching the spreadsheet header,
    trying CUSTOMER_GROUP_ALIASES (case-insensitive)."""
    candidates = CUSTOMER_GROUP_ALIASES.get(header, [header])
    # First try exact aliases.
    for alias in candidates:
        if frappe.db.exists("Customer Group", alias):
            return alias
    # Fallback: case-insensitive contains.
    all_groups = frappe.get_all("Customer Group", pluck="name")
    lower_map = {g.lower(): g for g in all_groups}
    for alias in candidates:
        if alias.lower() in lower_map:
            return lower_map[alias.lower()]
    # Last resort: any group containing the alias substring.
    for alias in candidates:
        for g in all_groups:
            if alias.lower() in g.lower():
                return g
    return None


def _resolve_territory(outlet: str) -> Optional[str]:
    candidates = TERRITORY_ALIASES.get(outlet, [outlet])
    for alias in candidates:
        if frappe.db.exists("Territory", alias):
            return alias
    all_terr = frappe.get_all("Territory", pluck="name")
    lower_map = {t.lower(): t for t in all_terr}
    for alias in candidates:
        if alias.lower() in lower_map:
            return lower_map[alias.lower()]
    return None


def _upsert_tier(item_code: str, customer_group: str, territory: str,
                 rate: float, currency: str = CURRENCY) -> tuple[str, str]:
    """Upsert one LPG Outlet Price Tier row. Returns (name, action)."""
    existing = frappe.get_all(
        "LPG Outlet Price Tier",
        filters={
            "item_code": item_code,
            "customer_group": customer_group,
            "territory": territory,
        },
        pluck="name",
        limit=1,
    )
    if existing:
        name = existing[0]
        doc = frappe.get_doc("LPG Outlet Price Tier", name)
        old_rate = float(doc.rate or 0)
        # Protected test row?
        if (PROTECT_PEDRO_RETAIL_TEST
                and item_code == "LPG-REFILL"
                and customer_group.lower() == "retail"
                and territory.lower() == "pedro"):
            return name, f"PROTECTED (keeping {old_rate:.0f})"
        if old_rate == rate and doc.currency == currency and doc.enabled == 1:
            return name, "UNCHANGED"
        doc.rate = rate
        doc.currency = currency
        doc.enabled = 1
        doc.save(ignore_permissions=True)
        return name, f"UPDATED ({old_rate:.0f}\u2192{rate:.0f})"

    doc = frappe.get_doc({
        "doctype": "LPG Outlet Price Tier",
        "item_code": item_code,
        "customer_group": customer_group,
        "territory": territory,
        "rate": rate,
        "currency": currency,
        "enabled": 1,
    })
    doc.insert(ignore_permissions=True)
    return doc.name, "CREATED"


# -----------------------------------------------------------------------------
# MAIN
# -----------------------------------------------------------------------------
def main():
    print("=" * 78)
    print(" Seed LPG Outlet Price Tier matrix from Pricelist.xlsx")
    print("=" * 78)

    if not frappe.db.exists("Item", ITEM_CODE):
        print(f"  ERROR: Item {ITEM_CODE!r} not found. Cannot seed tiers.")
        sys.exit(1)

    # ---- DIAGNOSTIC ---------------------------------------------------------
    print("\n[1/3] Customer Group resolution")
    print("-" * 78)
    group_map: dict[str, Optional[str]] = {}
    for header in CUSTOMER_GROUP_ALIASES.keys():
        resolved = _resolve_customer_group(header)
        group_map[header] = resolved
        marker = "OK " if resolved else "MISS"
        print(f"  [{marker}] spreadsheet {header!r:<14} -> ERPNext {resolved!r}")

    missing_groups = [h for h, r in group_map.items() if r is None]
    if missing_groups:
        print(f"\n  WARNING: {len(missing_groups)} customer group(s) not found: "
              f"{missing_groups}. Rows referencing them will be SKIPPED.")
        print("  Available Customer Groups on this site:")
        for g in frappe.get_all("Customer Group", pluck="name", order_by="name"):
            print(f"     - {g}")
        print("  Update CUSTOMER_GROUP_ALIASES in this script if names differ.")

    print("\n[2/3] Territory resolution")
    print("-" * 78)
    terr_map: dict[str, Optional[str]] = {}
    for outlet in MATRIX.keys():
        resolved = _resolve_territory(outlet)
        terr_map[outlet] = resolved
        marker = "OK " if resolved else "MISS"
        print(f"  [{marker}] outlet {outlet!r:<16} -> Territory {resolved!r}")

    missing_terr = [o for o, r in terr_map.items() if r is None]
    if missing_terr:
        print(f"\n  WARNING: {len(missing_terr)} territory(ies) not found: "
              f"{missing_terr}. Their rows will be SKIPPED.")

    # ---- SEED ---------------------------------------------------------------
    print("\n[3/3] Upserting tier rows")
    print("-" * 78)

    summary = {
        "CREATED": 0, "UPDATED": 0, "UNCHANGED": 0,
        "PROTECTED": 0, "SKIPPED": 0, "ERRORED": 0,
    }
    errors: list[tuple[str, str, str, str]] = []

    for outlet, prices in MATRIX.items():
        territory = terr_map.get(outlet)
        if not territory:
            for header in prices:
                summary["SKIPPED"] += 1
            continue
        for header, rate in prices.items():
            group = group_map.get(header)
            if not group:
                summary["SKIPPED"] += 1
                continue
            try:
                _name, action = _upsert_tier(
                    ITEM_CODE, group, territory, float(rate)
                )
                summary[action.split()[0]] = summary.get(action.split()[0], 0) + 1
                print(f"  [{action:<28}] {ITEM_CODE} / {group:<12} / "
                      f"{territory:<16} @ {CURRENCY} {rate}")
            except Exception as exc:  # noqa: BLE001
                summary["ERRORED"] += 1
                errors.append((ITEM_CODE, group, territory, str(exc)))
                print(f"  [ERROR] {ITEM_CODE} / {group} / {territory}: {exc}")

    frappe.db.commit()
    frappe.clear_cache()

    print("\n" + "-" * 78)
    print(" Summary:")
    for k, v in summary.items():
        if v:
            print(f"   {k:<10} {v}")
    if errors:
        print("\n Errors:")
        for item, g, t, e in errors:
            print(f"   - {item} / {g} / {t}: {e}")

    print("\n  PROTECT_PEDRO_RETAIL_TEST = {}".format(PROTECT_PEDRO_RETAIL_TEST))
    if PROTECT_PEDRO_RETAIL_TEST:
        print("  (Pedro Retail tier left at \u20a63,000 for ongoing UI testing.")
        print("   Flip PROTECT_PEDRO_RETAIL_TEST = False and re-run to set it to \u20a61,360.)")

    print("\n  Next: open POS Awesome, switch outlet/customer, confirm tier rates")
    print("  match this spreadsheet. CLIMAX GAS (Distributor) at Pedro should now")
    print("  quote \u20a61,140 (Lagos Distributor rate).")
    print("=" * 78)
    sys.exit(0 if not errors else 2)


# bench execute eval-scope fix (same trick as other Phase-5 scripts).
try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
