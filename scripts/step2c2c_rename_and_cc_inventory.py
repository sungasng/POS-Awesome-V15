"""
Phase 6 / Step 2c.2C: Cost Center inventory + rename ugly account names.

PART A: Renames 4 accounts created by Step 2c.2B with duplicated numbers:
    6221 - 6221 - HMO - Payable - SCL     -> 6221 - HMO - Payable - SCL
    6222 - 6222 - Cooperative Loan ...    -> 6222 - Cooperative Loan - Payable - SCL
    6223 - 6223 - Cooperative Contrib ... -> 6223 - Cooperative Contribution - Payable - SCL
    2900 - 2900 - Staff Loan Receivable.. -> 2900 - Staff Loan Receivable - SCL

PART B: Lists all leaf Cost Centers in /tmp/cost_center_inventory.md so we can
plan outlet-specific Operations cost centers for Step 2c.3.

Idempotent. Toggle DRY_RUN=True to preview.

Run:
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/feat/sungas-customizations/scripts/step2c2c_rename_and_cc_inventory.py" -o /tmp/step2c2c.py
    bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/step2c2c.py').read())"
"""

from __future__ import annotations

from pathlib import Path

import frappe


DRY_RUN = False

RENAMES = [
    ("6221 - 6221 - HMO - Payable - SCL",
     "6221 - HMO - Payable - SCL"),
    ("6222 - 6222 - Cooperative Loan - Payable - SCL",
     "6222 - Cooperative Loan - Payable - SCL"),
    ("6223 - 6223 - Cooperative Contribution - Payable - SCL",
     "6223 - Cooperative Contribution - Payable - SCL"),
    ("2900 - 2900 - Staff Loan Receivable - SCL",
     "2900 - Staff Loan Receivable - SCL"),
]


def rename_account(old: str, new: str, report: list[str]) -> None:
    if not frappe.db.exists("Account", old):
        if frappe.db.exists("Account", new):
            report.append(f"  = `{new}` already in clean form")
        else:
            report.append(f"  ! `{old}` not found")
        return
    if DRY_RUN:
        report.append(f"  ~ would-rename `{old}` -> `{new}`")
        return
    # Build a clean account_name like "6221 - HMO - Payable" (strip dup-number prefix)
    doc = frappe.get_doc("Account", old)
    new_account_name_value = " - ".join([
        doc.account_number,
        doc.account_name.split(" - ", 2)[-1] if doc.account_name.startswith(doc.account_number) else doc.account_name
    ])
    frappe.rename_doc("Account", old, new, force=True, merge=False)
    renamed = frappe.get_doc("Account", new)
    if renamed.account_name.startswith(f"{renamed.account_number} - {renamed.account_number}"):
        renamed.account_name = new_account_name_value
        renamed.save(ignore_permissions=True)
    report.append(f"  ~ renamed `{old}` -> `{new}`")


def main():
    print("=" * 72)
    print(f" Phase 6 / Step 2c.2C -- Rename + Cost Center inventory (DRY_RUN={DRY_RUN})")
    print("=" * 72)

    report: list[str] = []
    report.append("# Step 2c.2C -- Account renames + CC inventory")
    report.append("")
    report.append(f"_Generated: {frappe.utils.now_datetime()}_  ")
    report.append(f"_Site: {frappe.local.site} | DRY_RUN={DRY_RUN}_")
    report.append("")

    # --- PART A: Renames ---
    report.append("## A. Account renames")
    report.append("")
    for old, new in RENAMES:
        rename_account(old, new, report)
    report.append("")

    # --- PART B: Cost Center inventory ---
    report.append("## B. Leaf Cost Centers (all)")
    report.append("")
    ccs = frappe.get_all(
        "Cost Center",
        filters={"is_group": 0},
        fields=["name", "cost_center_name", "parent_cost_center"],
        order_by="name",
    )
    report.append(f"_{len(ccs)} leaf cost centers_")
    report.append("")
    report.append("| Cost Center | Parent |")
    report.append("|---|---|")
    for c in ccs:
        report.append(f"| `{c['name']}` | {c['parent_cost_center']} |")
    report.append("")

    # --- PART C: Per-outlet CC summary (looking for pattern) ---
    report.append("## C. Per-outlet Cost Center pattern analysis")
    report.append("")
    from collections import defaultdict
    by_outlet = defaultdict(list)
    OUTLETS = [
        "Headquarters", "Ikeja", "Pedro", "Oshodi", "Aseese", "Iju-Otta",
        "Osi-Otta", "Sefu", "Maba", "Ijoko", "Ebute", "Upper Mission",
        "Idokpa", "Ekehuan", "Okhuoromi", "Idowina", "Asaba",
        "Reclamation", "Eleme",
    ]
    for c in ccs:
        for outlet in OUTLETS:
            if outlet.lower().replace("-", "") in c["name"].lower().replace("-", ""):
                by_outlet[outlet].append(c["name"])
                break

    for outlet in OUTLETS:
        hits = by_outlet.get(outlet, [])
        if not hits:
            report.append(f"### {outlet}  ❌ (no CC found)")
        else:
            report.append(f"### {outlet}  ({len(hits)} CC)")
            for h in hits:
                report.append(f"  - `{h}`")
        report.append("")

    if not DRY_RUN:
        frappe.db.commit()

    p = Path("/tmp/step2c2c_renames_cc.md")
    p.write_text("\n".join(report), encoding="utf-8")
    print(f"\n[OK] wrote {p}")
    print("\n----- preview of Part C -----\n")
    in_c = False
    for line in report:
        if line.startswith("## C."):
            in_c = True
        if in_c:
            print(line)


try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
