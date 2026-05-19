"""
Phase 6 / Step 3a: FIX corrupted SSA bases.

The original /tmp/_payroll_roster.py read column 7 (Cola = 10% of Gross)
instead of column 3/7 (actual Gross), so all 217 SSA bases are 10x too low.

This script:
  1. Loads _payroll_roster_v2.py (corrected from STAFF PAYROLL FOR APRIL 2026.xls)
  2. Looks up each existing submitted SSA on 'Sungas Standard' from 2026-06-01
  3. For each: if current_base != correct_base, CANCEL the SSA and CREATE+SUBMIT
     a fresh one with the correct base (preserving employee, structure, from_date,
     payroll_cost_center).
  4. Idempotent -- re-running after success is a no-op.

Toggle DRY_RUN=True to preview.

Run:
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/feat/sungas-customizations/scripts/step3a_fix_ssa_bases.py" -o /tmp/step3a.py
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/feat/sungas-customizations/scripts/_payroll_roster_v2.py" -o /tmp/_payroll_roster_v2.py
    bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/step3a.py').read())"
"""

from __future__ import annotations
import re
import sys
from collections import defaultdict
from pathlib import Path

import frappe


DRY_RUN = False

STRUCTURE_NAME = "Sungas Standard"
FROM_DATE = "2026-06-01"
TOLERANCE = 0.01  # ignore sub-kobo float drift


def _tokenise(name: str) -> frozenset[str]:
    return frozenset(t for t in re.split(r"[^A-Za-z]+", (name or "").upper()) if t)


def lookup_employee(payroll_name: str, idx: dict):
    tokens = _tokenise(payroll_name)
    if tokens in idx:
        hits = idx[tokens]
        return hits[0] if len(hits) == 1 else None
    candidates = [
        cand for key, cands in idx.items() for cand in cands
        if tokens and (tokens <= key or key <= tokens) and len(tokens & key) >= 2
    ]
    return candidates[0] if len(candidates) == 1 else None


def main():
    print("=" * 72)
    print(f" Phase 6 / Step 3a -- FIX SSA bases (DRY_RUN={DRY_RUN})")
    print("=" * 72)

    sys.path.insert(0, "/tmp")
    try:
        from _payroll_roster_v2 import PAYROLL_APR_2026_V2 as ROSTER  # type: ignore
    except Exception as exc:
        print(f"  ! could not import /tmp/_payroll_roster_v2.py: {exc}")
        return

    report: list[str] = []
    report.append("# Step 3a -- Fix SSA bases (10x bug from Cola-col mis-read)")
    report.append("")
    report.append(f"_Generated: {frappe.utils.now_datetime()} | Site: {frappe.local.site} | DRY_RUN={DRY_RUN}_")
    report.append("")
    report.append(f"Roster (v2): **{len(ROSTER)}** employees, gross min={min(r['gross'] for r in ROSTER):,.2f}, max={max(r['gross'] for r in ROSTER):,.2f}")
    report.append("")

    # Build employee index from active employees
    idx = defaultdict(list)
    for emp in frappe.get_all(
        "Employee",
        filters={"status": "Active"},
        fields=["name", "employee_name", "designation", "department", "branch"],
    ):
        idx[_tokenise(emp["employee_name"] or "")].append(emp)

    unmatched = []
    correct = []
    needs_fix = []  # (emp_id, current_base, correct_base, payroll_name)

    for row in ROSTER:
        emp = lookup_employee(row["name"], idx)
        if not emp:
            unmatched.append(row["name"])
            continue
        emp_id = emp["name"]
        correct_base = float(row["gross"])

        ssa = frappe.get_all(
            "Salary Structure Assignment",
            filters={
                "employee": emp_id,
                "salary_structure": STRUCTURE_NAME,
                "from_date": FROM_DATE,
                "docstatus": 1,
            },
            fields=["name", "base"],
            limit=1,
        )
        if not ssa:
            unmatched.append(f"{row['name']} (emp matched but no submitted SSA)")
            continue

        ssa_row = ssa[0]
        current_base = float(ssa_row["base"] or 0)
        if abs(current_base - correct_base) <= TOLERANCE:
            correct.append(emp_id)
        else:
            needs_fix.append({
                "ssa_name": ssa_row["name"],
                "emp_id": emp_id,
                "emp_name": emp["employee_name"],
                "current_base": current_base,
                "correct_base": correct_base,
                "payroll_name": row["name"],
            })

    report.append(f"- SSAs already correct: **{len(correct)}**")
    report.append(f"- SSAs needing fix:     **{len(needs_fix)}**")
    report.append(f"- Roster rows unmatched: {len(unmatched)}")
    report.append("")

    if unmatched:
        report.append("## Unmatched (skipped):")
        for n in unmatched[:30]:
            report.append(f"  - {n}")
        if len(unmatched) > 30:
            report.append(f"  ... and {len(unmatched) - 30} more")
        report.append("")

    fixed = 0
    errors = []
    for fix in needs_fix:
        if DRY_RUN:
            continue
        try:
            # Cancel old
            old = frappe.get_doc("Salary Structure Assignment", fix["ssa_name"])
            old.cancel()
            # Create new
            new = frappe.get_doc({
                "doctype": "Salary Structure Assignment",
                "employee": fix["emp_id"],
                "salary_structure": STRUCTURE_NAME,
                "from_date": FROM_DATE,
                "base": fix["correct_base"],
                "company": frappe.defaults.get_user_default("Company") or frappe.get_all("Company", limit=1)[0]["name"],
            })
            new.insert(ignore_permissions=True)
            new.submit()
            fixed += 1
        except Exception as e:
            errors.append((fix["emp_id"], fix["payroll_name"], str(e)))

    if not DRY_RUN:
        frappe.db.commit()

    report.append(f"## Fix execution ({'DRY-RUN' if DRY_RUN else 'LIVE'})")
    report.append("")
    report.append(f"- Fixed: **{fixed}** / {len(needs_fix)}")
    report.append(f"- Errors: {len(errors)}")
    if errors:
        report.append("")
        report.append("Error details:")
        for emp_id, pname, err in errors[:20]:
            report.append(f"  - {emp_id} ({pname}): {err}")
    report.append("")

    # Show 10 biggest fixes for sanity-check
    sorted_fixes = sorted(needs_fix, key=lambda x: x["correct_base"], reverse=True)
    report.append("## Top 10 fixes (highest gross):")
    report.append("")
    report.append("| Employee | Name | Old base | New base | Δ |")
    report.append("|---|---|---:|---:|---:|")
    for fix in sorted_fixes[:10]:
        delta = fix["correct_base"] - fix["current_base"]
        report.append(
            f"| {fix['emp_id']} | {fix['emp_name']} | "
            f"{fix['current_base']:,.2f} | {fix['correct_base']:,.2f} | +{delta:,.2f} |"
        )
    report.append("")

    p = Path("/tmp/step3a_fix_ssa_bases.md")
    p.write_text("\n".join(report), encoding="utf-8")
    print(f"\n[OK] wrote {p}\n")
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
