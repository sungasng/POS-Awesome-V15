"""
Phase 6 / Step 2c.2 (PART A): Chart of Accounts inventory for payroll posting.

READ-ONLY. Surveys the CoA to find candidate accounts for each Salary Component
plus statutory payables. Output: /tmp/coa_inventory.md

Run:
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/feat/sungas-customizations/scripts/inventory_coa.py" -o /tmp/inventory_coa.py
    bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/inventory_coa.py').read())"
"""

from __future__ import annotations

from pathlib import Path

import frappe


SEARCH_TERMS = {
    # Earnings - expense accounts
    "Earnings / Salaries expense":
        ["salary", "salaries", "wages", "payroll"],
    "Transport allowance":
        ["transport"],
    "Housing allowance":
        ["housing", "rent"],
    "COLA":
        ["cola", "cost of living", "allowance"],
    "Medical / HMO":
        ["medical", "hmo", "health"],

    # Deductions - liability/payable accounts
    "Pension payable":
        ["pension"],
    "PAYE payable":
        ["paye", "tax payable", "withholding tax"],
    "NSITF payable":
        ["nsitf"],
    "Staff loan receivable":
        ["staff loan", "employee loan", "loan"],
    "Cooperative payable":
        ["coop", "cooperative"],
}


def search_accounts(terms: list[str]) -> list[dict]:
    """Return all leaf accounts matching any term (case-insensitive)."""
    hits = []
    seen = set()
    for term in terms:
        rows = frappe.get_all(
            "Account",
            filters={
                "is_group": 0,
                "account_name": ["like", f"%{term}%"],
            },
            fields=["name", "account_name", "account_type", "root_type", "parent_account"],
        )
        for r in rows:
            if r["name"] not in seen:
                seen.add(r["name"])
                hits.append(r)
    return hits


def main():
    print("=" * 72)
    print(" Phase 6 / Step 2c.2A -- Chart of Accounts inventory for payroll")
    print("=" * 72)

    out = []
    out.append("# CoA inventory for payroll GL mapping")
    out.append("")
    out.append(f"_Generated: {frappe.utils.now_datetime()}_  ")
    out.append(f"_Site: {frappe.local.site}_")
    out.append("")

    # Total leaf account count
    total = frappe.db.count("Account", {"is_group": 0})
    out.append(f"**Total leaf accounts**: {total}")
    out.append("")

    out.append("## Matches per component category")
    out.append("")

    for label, terms in SEARCH_TERMS.items():
        out.append(f"### {label}")
        out.append(f"_search terms: {', '.join(terms)}_")
        out.append("")
        hits = search_accounts(terms)
        if not hits:
            out.append("**(no matches)** — would need to be created")
        else:
            out.append("| Account | Type | Root | Parent |")
            out.append("|---|---|---|---|")
            for h in hits[:25]:
                out.append(
                    f"| `{h['name']}` | {h['account_type'] or '-'} | {h['root_type']} | {h['parent_account']} |"
                )
            if len(hits) > 25:
                out.append(f"| _...and {len(hits)-25} more_ | | | |")
        out.append("")

    # Top-level Liabilities tree for reference (so we know where to plant new payables)
    out.append("## Current Liability groups (to plant new payable accounts under)")
    out.append("")
    groups = frappe.get_all(
        "Account",
        filters={"is_group": 1, "root_type": "Liability"},
        fields=["name", "parent_account"],
        order_by="name",
    )
    out.append("| Group account | Parent |")
    out.append("|---|---|")
    for g in groups:
        out.append(f"| `{g['name']}` | {g['parent_account'] or '-'} |")
    out.append("")

    # Expense groups (where to plant salaries expense if missing)
    out.append("## Expense groups (where to plant new salary expense accounts)")
    out.append("")
    groups = frappe.get_all(
        "Account",
        filters={"is_group": 1, "root_type": "Expense"},
        fields=["name", "parent_account"],
        order_by="name",
    )
    out.append("| Group account | Parent |")
    out.append("|---|---|")
    for g in groups[:30]:
        out.append(f"| `{g['name']}` | {g['parent_account'] or '-'} |")
    if len(groups) > 30:
        out.append(f"| _...and {len(groups)-30} more_ | |")
    out.append("")

    # Cost Centers (leaf only, parents already shown in earlier inventory)
    out.append("## Leaf Cost Centers (for outlet-specific routing)")
    out.append("")
    ccs = frappe.get_all(
        "Cost Center",
        filters={"is_group": 0},
        fields=["name", "cost_center_name", "parent_cost_center"],
        order_by="name",
    )
    out.append(f"_{len(ccs)} leaf cost centers found._")
    out.append("")
    out.append("| Cost Center | Parent |")
    out.append("|---|---|")
    for c in ccs[:50]:
        out.append(f"| `{c['name']}` | {c['parent_cost_center']} |")
    if len(ccs) > 50:
        out.append(f"| _...and {len(ccs)-50} more_ | |")
    out.append("")

    p = Path("/tmp/coa_inventory.md")
    p.write_text("\n".join(out), encoding="utf-8")
    print(f"\n[OK] wrote {p}")
    print("\n----- preview -----\n")
    for line in out[:80]:
        print(line)
    if len(out) > 80:
        print("\n... (truncated, full file at /tmp/coa_inventory.md) ...")



try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
