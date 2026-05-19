"""
Phase 6 / Step 3b: Residual audit + clean-up of unmatched roster rows.

Investigates the 8 unmatched names from step 3a:
  - 'Pension payable for the Month'                   -> garbage row, skip
  - OBI VICTOR, TAKPOR EFE, EMMANUELLA BENJAMIN       -> Employees exist but no SSA on 'Sungas Standard'
  - DOMINION ROLAND, BULUS SATI, GODWIN SAVIOUR,
    ISAAC ONWUZULUIGBO                                -> No employee found via _tokenise

Actions (idempotent):
  1. Find each unmatched name via fuzzy lookup (try first+last, last+first, partial)
  2. For 'matched but no SSA': CREATE+SUBMIT a Salary Structure Assignment with
     the correct base from roster v2, from_date=2026-06-01
  3. For 'truly unmatched': list candidates with fuzzy score so user can confirm
     the right ERP record, or flag for HR to onboard

Run:
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/feat/sungas-customizations/scripts/step3b_residual_audit.py" -o /tmp/step3b.py
    bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/step3b.py').read())"
"""

from __future__ import annotations
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

import frappe


DRY_RUN = True  # Default to dry-run; flip to False to create SSAs for the 3 matched

STRUCTURE_NAME = "Sungas Standard"
FROM_DATE = "2026-06-01"

UNMATCHED_NAMES = [
    "OBI VICTOR",
    "TAKPOR EFE",
    "EMMANUELLA BENJAMIN",
    "DOMINION ROLAND",
    "BULUS SATI",
    "GODWIN SAVIOUR",
    "ISAAC ONWUZULUIGBO",
]


def _norm(s: str) -> str:
    return re.sub(r"[^A-Z]+", " ", (s or "").upper()).strip()


def fuzzy_candidates(target: str, employees: list[dict], top_n: int = 5) -> list[tuple[float, dict]]:
    norm_target = _norm(target)
    target_tokens = set(norm_target.split())
    scored = []
    for emp in employees:
        norm_emp = _norm(emp["employee_name"] or "")
        # Score = ratio + token-overlap bonus
        ratio = SequenceMatcher(None, norm_target, norm_emp).ratio()
        emp_tokens = set(norm_emp.split())
        overlap = len(target_tokens & emp_tokens)
        score = ratio + (0.1 * overlap)
        scored.append((score, emp))
    scored.sort(key=lambda x: -x[0])
    return scored[:top_n]


def main():
    print("=" * 72)
    print(f" Phase 6 / Step 3b -- Residual audit (DRY_RUN={DRY_RUN})")
    print("=" * 72)

    sys.path.insert(0, "/tmp")
    try:
        from _payroll_roster_v2 import PAYROLL_APR_2026_V2 as ROSTER  # type: ignore
    except Exception as exc:
        print(f"  ! could not import /tmp/_payroll_roster_v2.py: {exc}")
        return

    # Build roster lookup by normalised name
    roster_by_norm = {}
    for r in ROSTER:
        roster_by_norm[_norm(r["name"])] = r

    active_emps = frappe.get_all(
        "Employee",
        filters={"status": "Active"},
        fields=["name", "employee_name", "designation", "department", "branch"],
    )

    report: list[str] = []
    report.append("# Step 3b -- Residual audit of unmatched roster rows")
    report.append("")
    report.append(f"_Generated: {frappe.utils.now_datetime()} | Site: {frappe.local.site} | DRY_RUN={DRY_RUN}_")
    report.append("")

    created = 0
    needs_user = 0
    company = frappe.defaults.get_user_default("Company") or frappe.get_all("Company", limit=1)[0]["name"]

    for payroll_name in UNMATCHED_NAMES:
        report.append(f"## `{payroll_name}`")
        report.append("")
        roster_row = roster_by_norm.get(_norm(payroll_name))
        if not roster_row:
            report.append("  ! NOT in roster v2 -- skipping")
            report.append("")
            continue
        report.append(f"  Roster: outlet={roster_row['outlet']!r}, position={roster_row['position']!r}, gross=₦{roster_row['gross']:,.2f}")

        # Find best fuzzy match
        cands = fuzzy_candidates(payroll_name, active_emps, top_n=5)
        report.append("  Top 5 ERP candidates by fuzzy score:")
        for score, emp in cands:
            existing_ssa = frappe.db.exists("Salary Structure Assignment", {
                "employee": emp["name"],
                "salary_structure": STRUCTURE_NAME,
                "from_date": FROM_DATE,
                "docstatus": 1,
            })
            ssa_marker = " [HAS SSA]" if existing_ssa else " [no SSA]"
            report.append(f"    {score:.3f}  {emp['name']:15s}  {emp['employee_name']:35s}  desig={emp['designation']!r}{ssa_marker}")

        # Auto-create SSA if top match score >= 0.85 AND no existing SSA on Sungas Standard
        top_score, top_emp = cands[0]
        if top_score >= 0.85:
            has_ssa = frappe.db.exists("Salary Structure Assignment", {
                "employee": top_emp["name"],
                "salary_structure": STRUCTURE_NAME,
                "from_date": FROM_DATE,
                "docstatus": 1,
            })
            if has_ssa:
                report.append(f"  = top match ({top_emp['name']}) already has SSA -- skip")
            else:
                report.append(f"  → AUTO-ACTION: create SSA for {top_emp['name']} ({top_emp['employee_name']})")
                report.append(f"     base = ₦{roster_row['gross']:,.2f}")
                if DRY_RUN:
                    report.append("     (DRY_RUN -- not created)")
                else:
                    try:
                        doc = frappe.get_doc({
                            "doctype": "Salary Structure Assignment",
                            "employee": top_emp["name"],
                            "salary_structure": STRUCTURE_NAME,
                            "from_date": FROM_DATE,
                            "base": roster_row["gross"],
                            "company": company,
                        }).insert(ignore_permissions=True)
                        doc.submit()
                        report.append(f"     ✓ created+submitted {doc.name}")
                        created += 1
                    except Exception as e:
                        report.append(f"     ! ERROR: {e}")
        else:
            report.append(f"  ⚠ top match score only {top_score:.3f} -- needs human confirmation")
            needs_user += 1
        report.append("")

    if not DRY_RUN:
        frappe.db.commit()

    report.append("---")
    report.append(f"Summary: created={created}, needs user review={needs_user}")
    report.append("")

    p = Path("/tmp/step3b_residual_audit.md")
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
