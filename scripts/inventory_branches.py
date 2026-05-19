"""
Phase 6 / Step 2a-pre: Branch + Territory + Department + Cost Center inventory.

READ-ONLY. Dumps the current state of all 4 master tables so we can decide
on canonical spellings before Step 2a writes anything.

Also flags mismatches between:
  - the 19 outlet names in April 2026 payroll
  - the Branch names currently in ERP
  - the Territory names currently in ERP

Output: /tmp/branch_inventory.md

Run:
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/feat/sungas-customizations/scripts/inventory_branches.py" -o /tmp/inventory_branches.py
    bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/inventory_branches.py').read())"
"""

from __future__ import annotations

import sys
from pathlib import Path

import frappe


PAYROLL_OUTLETS = [
    "HEADQUATERS", "IKEJA", "PEDRO", "OSHODI", "ASEESE", "IJU-OTA",
    "OSI-OTA", "SEFU", "MABA", "IJOKO", "EBUTE", "UPPER MISSION",
    "IDOKPA", "EKEHUAN", "OKHORUOMI", "IDOWINA", "ASABA", "RECLAMATION",
    "ELEME", "CASH SALARY",
]


def _fuzzy_match(payroll_name: str, candidates: list[str]) -> list[str]:
    """Return any candidate that shares >= 4 chars of common substring (ignoring case/hyphens/spaces)."""
    def norm(s: str) -> str:
        return s.upper().replace("-", "").replace(" ", "")
    pn = norm(payroll_name)
    hits = []
    for c in candidates:
        cn = norm(c)
        # bidirectional containment or first 5 chars match
        if pn[:5] and cn[:5] and (pn[:5] == cn[:5] or pn in cn or cn in pn):
            hits.append(c)
    return hits


def main():
    print("=" * 72)
    print(" Phase 6 / Step 2a-pre -- Branch/Territory/Dept/Cost Center inventory")
    print("=" * 72)

    out = []
    out.append("# Sungas -- Branch/Territory/Dept/Cost Center inventory")
    out.append("")
    out.append(f"_Generated: {frappe.utils.now_datetime()}_  ")
    out.append(f"_Site: {frappe.local.site}_")
    out.append("")

    # ----- Branches -----
    branches = frappe.get_all("Branch", fields=["name", "branch"], order_by="branch")
    out.append(f"## 1. Branches ({len(branches)})")
    out.append("")
    out.append("| Name (ID) | Label |")
    out.append("|---|---|")
    for b in branches:
        out.append(f"| `{b['name']}` | {b.get('branch') or '-'} |")
    out.append("")

    # ----- Territories -----
    territories = frappe.get_all("Territory", fields=["name", "parent_territory"], order_by="name")
    out.append(f"## 2. Territories ({len(territories)})")
    out.append("")
    out.append("| Name | Parent |")
    out.append("|---|---|")
    for t in territories:
        out.append(f"| `{t['name']}` | {t.get('parent_territory') or '-'} |")
    out.append("")

    # ----- Departments -----
    departments = frappe.get_all("Department", fields=["name", "department_name", "parent_department"], order_by="name")
    out.append(f"## 3. Departments ({len(departments)})")
    out.append("")
    out.append("| Name | Label | Parent |")
    out.append("|---|---|---|")
    for d in departments:
        out.append(f"| `{d['name']}` | {d.get('department_name') or '-'} | {d.get('parent_department') or '-'} |")
    out.append("")

    # ----- Designations -----
    designations = frappe.get_all("Designation", fields=["name"], order_by="name")
    out.append(f"## 4. Designations ({len(designations)})")
    out.append("")
    out.append("| Name |")
    out.append("|---|")
    for d in designations:
        out.append(f"| `{d['name']}` |")
    out.append("")

    # ----- Cost Centers (leaf only) -----
    ccs = frappe.get_all(
        "Cost Center",
        fields=["name", "cost_center_name", "is_group", "parent_cost_center"],
        filters={"is_group": 0},
        order_by="name",
    )
    out.append(f"## 5. Cost Centers - leaf only ({len(ccs)})")
    out.append("")
    out.append("| Name | Label | Parent |")
    out.append("|---|---|---|")
    for c in ccs:
        out.append(f"| `{c['name']}` | {c.get('cost_center_name') or '-'} | {c.get('parent_cost_center') or '-'} |")
    out.append("")

    # ----- Mismatch matrix: payroll outlet vs ERP -----
    out.append("## 6. Payroll outlet -> ERP mapping (must be 1:1 before Step 2a)")
    out.append("")
    out.append("Legend: `[OK]`=exact match | `[FUZZY]`=likely match w/ spelling diff | `[MISS]`=no match")
    out.append("")
    out.append("| Payroll outlet | Branch match(es) | Territory match(es) | Cost Center match(es) |")
    out.append("|---|---|---|---|")
    branch_labels = [b.get("branch") or b["name"] for b in branches]
    territory_names = [t["name"] for t in territories]
    cc_names = [c["name"] for c in ccs]

    def _flag_status(payroll: str, hits: list[str]) -> str:
        if not hits:
            return "**[MISS]**"
        for h in hits:
            if h.upper().replace("-", "").replace(" ", "") == payroll.upper().replace("-", "").replace(" ", ""):
                return f"**[OK]** {h}"
        return "**[FUZZY]** " + " / ".join(hits)

    for outlet in PAYROLL_OUTLETS:
        b_hits = _fuzzy_match(outlet, branch_labels)
        t_hits = _fuzzy_match(outlet, territory_names)
        c_hits = _fuzzy_match(outlet, cc_names)
        out.append(f"| {outlet} | {_flag_status(outlet, b_hits)} | {_flag_status(outlet, t_hits)} | {_flag_status(outlet, c_hits)} |")
    out.append("")

    # ----- Mismatch table (the ones we need to fix) -----
    out.append("## 7. Outlets needing spelling harmonisation")
    out.append("")
    needs_fix = []
    for outlet in PAYROLL_OUTLETS:
        if outlet == "CASH SALARY":
            continue
        b_hits = _fuzzy_match(outlet, branch_labels)
        ok_branch = any(h.upper().replace("-", "").replace(" ", "") == outlet.upper().replace("-", "").replace(" ", "") for h in b_hits)
        if not ok_branch:
            needs_fix.append((outlet, b_hits))
    if not needs_fix:
        out.append("_None._ 🎉 All payroll outlets map cleanly to a Branch.")
    else:
        out.append("| Payroll outlet | Closest Branch | Proposed canonical |")
        out.append("|---|---|---|")
        for o, hits in needs_fix:
            closest = hits[0] if hits else "(none)"
            out.append(f"| `{o}` | `{closest}` | _decide_ |")
    out.append("")

    p = Path("/tmp/branch_inventory.md")
    p.write_text("\n".join(out), encoding="utf-8")
    print(f"\n[OK] wrote {p} ({sum(len(line) for line in out):,} chars)")
    print("\n----- last 50 lines preview -----\n")
    for line in out[-50:]:
        print(line)


try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
