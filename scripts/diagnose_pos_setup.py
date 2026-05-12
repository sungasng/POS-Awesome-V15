"""
Diagnose what's available on the Frappe site so we can create POS Profile(s)
with sensible defaults.

Prints, for `sungasmis.v.frappe.cloud`:
    - Companies (+ default currency / abbreviation)
    - Price Lists (selling)
    - Warehouses (active)
    - Cost Centers (leaf)
    - Modes of Payment (enabled)
    - Customer Groups (leaf)
    - Currencies enabled
    - User counts by LPG role
    - The 8 newly-created cashier emails (to confirm they made it in)

Run on bench:
    bench --site sungasmis.v.frappe.cloud execute \\
        "exec(open('/tmp/diagnose_pos_setup.py').read())"
"""

from __future__ import annotations

import sys

import frappe


SECTION_RULE = "-" * 72


def _section(title: str) -> None:
    print()
    print(SECTION_RULE)
    print(f"  {title}")
    print(SECTION_RULE)


def main():
    print("=" * 72)
    print(" POS Profile setup diagnostic")
    print("=" * 72)

    _section("Companies")
    companies = frappe.get_all(
        "Company",
        fields=["name", "default_currency", "abbr", "country"],
    )
    if not companies:
        print("  !! NO COMPANIES — must create one before POS Profile.")
    for c in companies:
        print(f"  - {c.name:<40}  cur={c.default_currency or '-':<5} "
              f"abbr={c.abbr or '-':<6}  country={c.country or '-'}")

    _section("Selling Price Lists (enabled)")
    pls = frappe.get_all(
        "Price List",
        filters={"selling": 1, "enabled": 1},
        fields=["name", "currency"],
    )
    for p in pls:
        print(f"  - {p.name:<40}  cur={p.currency or '-'}")
    if not pls:
        print("  (none — POS Profile requires a selling price list)")

    _section("Warehouses (non-group, active)")
    whs = frappe.get_all(
        "Warehouse",
        filters={"is_group": 0, "disabled": 0},
        fields=["name", "warehouse_name", "company"],
        order_by="company, name",
    )
    print(f"  total: {len(whs)}")
    for w in whs[:50]:
        print(f"  - {w.name:<50}  {w.company or '-'}")
    if len(whs) > 50:
        print(f"  ... and {len(whs) - 50} more (showing first 50)")

    _section("Cost Centers (leaf)")
    ccs = frappe.get_all(
        "Cost Center",
        filters={"is_group": 0},
        fields=["name", "cost_center_name", "company"],
        order_by="company, name",
    )
    print(f"  total: {len(ccs)}")
    for c in ccs[:50]:
        print(f"  - {c.name:<50}  {c.company or '-'}")
    if len(ccs) > 50:
        print(f"  ... and {len(ccs) - 50} more (showing first 50)")

    _section("Modes of Payment (enabled)")
    mps = frappe.get_all(
        "Mode of Payment",
        filters={"enabled": 1},
        fields=["name", "type"],
        order_by="name",
    )
    for m in mps:
        print(f"  - {m.name:<40}  type={m.type or '-'}")
    if not mps:
        print("  (none — POS Profile requires at least one)")

    _section("Customer Groups (leaf)")
    cgs = frappe.get_all(
        "Customer Group",
        filters={"is_group": 0},
        fields=["name"],
        order_by="name",
    )
    print(f"  total: {len(cgs)}")
    for c in cgs[:40]:
        print(f"  - {c.name}")
    if len(cgs) > 40:
        print(f"  ... and {len(cgs) - 40} more")

    _section("Territories (leaf)")
    terrs = frappe.get_all(
        "Territory",
        filters={"is_group": 0},
        fields=["name"],
        order_by="name",
    )
    print(f"  total: {len(terrs)}")
    for t in terrs[:40]:
        print(f"  - {t.name}")
    if len(terrs) > 40:
        print(f"  ... and {len(terrs) - 40} more")

    _section("Users by LPG role")
    for role in ("LPG POS User", "LPG Plant Manager",
                 "LPG Head of Sales", "LPG Head of Finance"):
        n = frappe.db.count("Has Role", {"role": role, "parenttype": "User"})
        print(f"  {role:<25}  users={n}")

    _section("The 8 newly-created cashier accounts")
    targets = [
        "bolanle.ayodele@sungas.org",
        "bolajoko.abilawon@sungas.org",
        "gift.okotogbo@sungas.org",
        "racheal.moses@sungas.org",
        "shima.justine@sungas.org",
        "gift.odihi@sungas.org",
        "kaosara.kareem@sungas.org",
        "oluwaseyi.olawole@sungas.org",
    ]
    for email in targets:
        if frappe.db.exists("User", email):
            roles = frappe.get_all(
                "Has Role",
                filters={"parent": email, "parenttype": "User"},
                pluck="role",
            )
            enabled = frappe.db.get_value("User", email, "enabled")
            has_lpg = "LPG POS User" in roles
            print(f"  OK   {email}  enabled={enabled}  LPG_POS_User={has_lpg}  total_roles={len(roles)}")
        else:
            print(f"  MISS {email}  (user not found — run create_missing_cashiers.py)")

    _section("Existing POS Profiles")
    profs = frappe.get_all("POS Profile", fields=["name", "company", "disabled"])
    if not profs:
        print("  (none — POS Awesome cannot load until at least one exists)")
    for p in profs:
        users = frappe.db.count(
            "POS Profile User", {"parent": p.name}
        )
        print(f"  - {p.name:<40}  company={p.company or '-':<25}  "
              f"disabled={p.disabled}  applicable_users={users}")

    _section("DONE")
    print("Paste the entire output above back to the agent.")
    print("=" * 72)
    sys.exit(0)


main()
