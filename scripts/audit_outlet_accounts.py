"""
Phase-5 follow-up: audit the bench's Chart of Accounts, Cost Centers,
Accounting Dimensions, and Item income mappings BEFORE writing the
POS Profile / Print Format / dimensions config scripts.

This is a strict read-only script. It does not insert / update / delete
anything. Output goes to stdout; paste it back to the agent.

Run on bench:
    curl -fsSL https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/develop/scripts/audit_outlet_accounts.py \
      -o /tmp/audit_outlet_accounts.py && \
    bench --site sungasmis.v.frappe.cloud execute \
      "exec(open('/tmp/audit_outlet_accounts.py').read())"
"""

from __future__ import annotations

import frappe

COMPANY = "SUNGAS COMPANY LIMITED"

# Outlet tokens (must mirror the spreadsheet headers - keep in sync with
# seed_all_lpg_tier_rates.py MATRIX).
OUTLETS = [
    "Maba", "Sefu", "Ebutte", "Aseese",
    "Itele", "Iju-Otta", "Osi-Otta", "Ijoko",
    "Ikeja", "Oworo", "Pedro", "Bolade", "Mafoluku",
    "Eleme", "Reclamation",
    "Ekehuan", "Upper Mission", "Idowina", "Idokpa", "Okhuoromi",
    "Asaba",
]

# Regions per spreadsheet rev 2026-02.
REGIONS = ["Ogun 1", "Ogun 2", "Lagos 1", "Rivers 1", "Edo 1", "Delta 1"]


def _hr(title: str) -> None:
    print("\n" + "=" * 78)
    print("  " + title)
    print("=" * 78)


def section_cost_centers() -> None:
    _hr("1. Cost Centers (looking for one per outlet, name contains outlet)")
    rows = frappe.get_all(
        "Cost Center",
        filters={"company": COMPANY, "is_group": 0, "disabled": 0},
        fields=["name", "cost_center_name", "parent_cost_center"],
        order_by="name",
    )
    print(f"  Total leaf cost centers: {len(rows)}")
    sales_marketing = [r for r in rows if "sales and marketing" in r["cost_center_name"].lower()]
    print(f"  Cost Centers containing 'Sales and Marketing': {len(sales_marketing)}")
    print()
    for outlet in OUTLETS:
        token = outlet.lower().replace("-", "").replace(" ", "")
        matches = [
            r for r in sales_marketing
            if token in r["cost_center_name"].lower().replace("-", "").replace(" ", "")
        ]
        if matches:
            print(f"  [OK ] {outlet:<16} -> {matches[0]['name']}")
        else:
            print(f"  [MISS] {outlet:<16} -> no 'Sales and Marketing' cost center found")
    print()
    print("  Sample of ALL leaf Sales and Marketing cost centers (first 30):")
    for r in sales_marketing[:30]:
        print(f"    - {r['name']}")


def section_cash_pos_transfer_accounts() -> None:
    for label, search in (
        ("Cash Sales", "%cash sales%"),
        ("Incoming Transfer", "%incoming transfer%"),
        ("Incoming POS", "%incoming pos%"),
    ):
        _hr(f"2. {label} Accounts (looking for one per outlet)")
        rows = frappe.get_all(
            "Account",
            filters={"company": COMPANY, "is_group": 0, "disabled": 0,
                     "account_name": ["like", search]},
            fields=["name", "account_name", "account_type", "root_type"],
            order_by="account_name",
        )
        print(f"  Total accounts matching '{search}': {len(rows)}")
        print()
        for outlet in OUTLETS:
            token = outlet.lower().replace("-", "").replace(" ", "")
            matches = [
                r for r in rows
                if token in r["account_name"].lower().replace("-", "").replace(" ", "")
            ]
            if matches:
                print(f"  [OK ] {outlet:<16} -> {matches[0]['name']}")
            else:
                print(f"  [MISS] {outlet:<16}")
        print()
        if not rows:
            print("  (no rows; nothing to enumerate)")
        else:
            print(f"  Sample of ALL '{search}' accounts (first 30):")
            for r in rows[:30]:
                print(f"    - {r['name']:<55} ({r['account_type']})")


def section_revenue_accounts() -> None:
    _hr("3. Revenue / Income accounts")
    rows = frappe.get_all(
        "Account",
        filters={"company": COMPANY, "is_group": 0, "disabled": 0,
                 "root_type": "Income"},
        fields=["name", "account_name", "account_type"],
        order_by="name",
    )
    print(f"  Total Income leaf accounts: {len(rows)}")
    for r in rows[:50]:
        print(f"    - {r['name']:<55} type={r['account_type']!r}")
    if len(rows) > 50:
        print(f"    ... and {len(rows) - 50} more (truncated)")


def section_round_off() -> None:
    _hr("4. Round Off / Write Off / Misc")
    rows = frappe.get_all(
        "Account",
        filters={"company": COMPANY, "is_group": 0, "disabled": 0},
        or_filters=[
            ["account_type", "=", "Round Off"],
            ["account_name", "like", "%round off%"],
            ["account_name", "like", "%write off%"],
            ["account_name", "like", "%rounding%"],
        ],
        fields=["name", "account_name", "account_type", "root_type"],
        order_by="name",
    )
    for r in rows:
        print(f"  - {r['name']:<55} type={r['account_type']!r} root={r['root_type']}")
    co = frappe.db.get_value(
        "Company", COMPANY,
        ["round_off_account", "write_off_account", "default_income_account",
         "default_cash_account", "default_bank_account", "cost_center"],
        as_dict=True,
    )
    print("\n  Company defaults:")
    for k, v in (co or {}).items():
        print(f"    {k:<28} = {v}")


def section_accounting_dimensions() -> None:
    _hr("5. Accounting Dimensions")
    if not frappe.db.exists("DocType", "Accounting Dimension"):
        print("  Accounting Dimension doctype not available on this bench. Skipping.")
        return
    rows = frappe.get_all(
        "Accounting Dimension",
        fields=["name", "document_type", "label", "fieldname", "disabled"],
        order_by="name",
    )
    if not rows:
        print("  (no Accounting Dimensions configured yet)")
    for r in rows:
        print(f"  - {r['name']:<35} doctype={r['document_type']:<20} "
              f"label={r['label']:<20} field={r['fieldname']} "
              f"disabled={r['disabled']}")
    # Dimension defaults at Company level.
    if frappe.db.exists("DocType", "Accounting Dimension Detail"):
        defaults = frappe.get_all(
            "Accounting Dimension Detail",
            filters={"company": COMPANY},
            fields=["parent", "company", "default_dimension",
                    "mandatory_for_bs", "mandatory_for_pl"],
        )
        print(f"\n  Company-level dimension defaults: {len(defaults)}")
        for d in defaults:
            print(f"    parent={d['parent']:<28} default={d['default_dimension']:<22} "
                  f"mand_BS={d['mandatory_for_bs']} mand_PL={d['mandatory_for_pl']}")


def section_branch_doctype() -> None:
    _hr("6. Branch doctype (HRMS)")
    if not frappe.db.exists("DocType", "Branch"):
        print("  Branch doctype not installed (HRMS not enabled here).")
        return
    rows = frappe.get_all("Branch", fields=["name", "branch"], order_by="name")
    print(f"  Total branches: {len(rows)}")
    for r in rows[:30]:
        print(f"    - {r['name']}")
    if len(rows) > 30:
        print(f"    ... and {len(rows) - 30} more")


def section_region_doctype() -> None:
    _hr("7. Region / Custom dimension candidates")
    for dt in ("Region", "Sungas Region", "Sales Region"):
        if frappe.db.exists("DocType", dt):
            rows = frappe.get_all(dt, fields=["name"], order_by="name")
            print(f"  {dt}: {len(rows)} entries")
            for r in rows[:20]:
                print(f"    - {r['name']}")
            break
    else:
        print("  No Region-like doctype yet (we'll need to create one).")


def section_item_defaults() -> None:
    _hr("8. Item income account mappings")
    item_codes = ["LPG-REFILL", "STO-LPG-2021-00001"]
    for code in item_codes:
        if not frappe.db.exists("Item", code):
            print(f"  [skip] Item {code!r} not present.")
            continue
        defaults = frappe.get_all(
            "Item Default",
            filters={"parent": code, "company": COMPANY},
            fields=["company", "income_account", "expense_account",
                    "default_warehouse", "default_supplier"],
        )
        print(f"  Item {code!r}: {len(defaults)} Item Default rows")
        for d in defaults:
            print(f"    - income={d['income_account'] or '(none)':<35} "
                  f"expense={d['expense_account'] or '(none)':<35} "
                  f"warehouse={d['default_warehouse']}")

    print()
    print("  Item Group income account defaults (parent=Item Group):")
    groups = frappe.get_all(
        "Item Group",
        filters={"is_group": 0},
        fields=["name", "parent_item_group"],
        limit=15,
    )
    for g in groups:
        defaults = frappe.get_all(
            "Item Default",
            filters={"parent": g["name"], "company": COMPANY},
            fields=["income_account"],
            limit=1,
        )
        ia = defaults[0]["income_account"] if defaults else "(none)"
        print(f"    - {g['name']:<30} parent={g['parent_item_group']:<18} income={ia}")


def section_pos_profile() -> None:
    _hr("9. POS Profile - Pedro (Test) current config")
    name = "POS - Pedro (Test)"
    if not frappe.db.exists("POS Profile", name):
        print(f"  {name!r} missing.")
        return
    p = frappe.get_doc("POS Profile", name)
    snapshot = {
        "warehouse": p.warehouse,
        "company": p.company,
        "cost_center": getattr(p, "cost_center", None),
        "currency": p.currency,
        "selling_price_list": p.selling_price_list,
        "customer_group": getattr(p, "customer_group", None),
        "write_off_account": getattr(p, "write_off_account", None),
        "write_off_cost_center": getattr(p, "write_off_cost_center", None),
        "account_for_change_amount": getattr(p, "account_for_change_amount", None),
        "income_account": getattr(p, "income_account", None),
        "tax_category": getattr(p, "tax_category", None),
        "letter_head": getattr(p, "letter_head", None),
        "print_format": getattr(p, "print_format", None),
        "print_format_for_online": getattr(p, "print_format_for_online", None),
    }
    for k, v in snapshot.items():
        print(f"    {k:<28} = {v}")
    print(f"  Payments table ({len(p.payments)} rows):")
    for pay in p.payments:
        print(f"    - mode={pay.mode_of_payment:<18} default={pay.default} "
              f"account={pay.account or '(use MoP default)'}")


def section_print_formats() -> None:
    _hr("10. Existing Print Formats for POS Invoice")
    rows = frappe.get_all(
        "Print Format",
        filters={"doc_type": "POS Invoice"},
        fields=["name", "module", "standard", "print_format_type", "disabled"],
        order_by="name",
    )
    print(f"  Total: {len(rows)}")
    for r in rows:
        print(f"    - {r['name']:<45} type={r['print_format_type']:<8} "
              f"standard={r['standard']} disabled={r['disabled']}")


def main() -> None:
    print("=" * 78)
    print(f"  Phase-5 audit — {COMPANY}")
    print("=" * 78)
    section_cost_centers()
    section_cash_pos_transfer_accounts()
    section_revenue_accounts()
    section_round_off()
    section_accounting_dimensions()
    section_branch_doctype()
    section_region_doctype()
    section_item_defaults()
    section_pos_profile()
    section_print_formats()
    print("\n" + "=" * 78)
    print("  Done. Paste this entire output back to the agent.")
    print("=" * 78)


try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
