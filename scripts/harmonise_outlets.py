"""
Phase 6 / Step 2a-pre-fix: Harmonise outlet spellings.

Creates the 4 Branches + 4 Territories that the April 2026 payroll references
but which are missing or misspelled in ERP.

Idempotent. Safe to re-run. Toggle DRY_RUN=True to preview.

The 4 missing outlets:
    Excel name     ERP canonical    Comment
    HEADQUATERS    Headquarters     Excel typo of HEADQUARTERS
    OSHODI         Oshodi           Missing from ERP
    EBUTE          Ebute            Missing from ERP
    OKHORUOMI      Okhuoromi        Both Excel + ERP missing; using clean spelling

Output: /tmp/harmonise_outlets.md

Run:
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/feat/sungas-customizations/scripts/harmonise_outlets.py" -o /tmp/harmonise_outlets.py
    bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/harmonise_outlets.py').read())"
"""

from __future__ import annotations

from pathlib import Path

import frappe


DRY_RUN = False

NEW_OUTLETS = [
    {"branch": "Headquarters", "parent_territory": None},
    {"branch": "Oshodi",       "parent_territory": "All Territories"},
    {"branch": "Ebute",        "parent_territory": "All Territories"},
    {"branch": "Okhuoromi",    "parent_territory": "All Territories"},
]


def upsert_branch(branch_name: str, report: list[str]) -> None:
    if frappe.db.exists("Branch", branch_name):
        report.append(f"  = Branch `{branch_name}` already exists")
        return
    if DRY_RUN:
        report.append(f"  + would-insert Branch `{branch_name}`")
        return
    frappe.get_doc({"doctype": "Branch", "branch": branch_name}).insert(ignore_permissions=True)
    report.append(f"  + Branch `{branch_name}` inserted")


def upsert_territory(territory_name: str, parent: str | None, report: list[str]) -> None:
    if frappe.db.exists("Territory", territory_name):
        report.append(f"  = Territory `{territory_name}` already exists")
        return
    if DRY_RUN:
        report.append(f"  + would-insert Territory `{territory_name}` (parent={parent})")
        return
    doc = {
        "doctype": "Territory",
        "territory_name": territory_name,
        "is_group": 0,
    }
    if parent and frappe.db.exists("Territory", parent):
        doc["parent_territory"] = parent
    frappe.get_doc(doc).insert(ignore_permissions=True)
    report.append(f"  + Territory `{territory_name}` inserted (parent={parent or '-'})")


def main():
    print("=" * 72)
    print(f" Phase 6 / Step 2a-pre-fix -- outlet harmonisation (DRY_RUN={DRY_RUN})")
    print("=" * 72)

    report: list[str] = []
    report.append("# Outlet harmonisation")
    report.append("")
    report.append(f"_Generated: {frappe.utils.now_datetime()}_  ")
    report.append(f"_Site: {frappe.local.site} | DRY_RUN={DRY_RUN}_")
    report.append("")

    report.append("## Branches")
    report.append("")
    for o in NEW_OUTLETS:
        upsert_branch(o["branch"], report)
    report.append("")

    report.append("## Territories")
    report.append("")
    for o in NEW_OUTLETS:
        upsert_territory(o["branch"], o["parent_territory"], report)
    report.append("")

    if not DRY_RUN:
        frappe.db.commit()

    p = Path("/tmp/harmonise_outlets.md")
    p.write_text("\n".join(report), encoding="utf-8")
    print(f"\n[OK] wrote {p}")
    print()
    for line in report:
        print(line)


try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
