"""
Phase 6 / Step 8b -- Restore empty formulas on 'Sungas Standard' structure rows.

Cause analysis
--------------
Submitted structure 'Sungas Standard' has rows 1-5 (earnings + deductions)
with empty `formula` and `condition` fields. The canonical formulas STILL
live on the Salary Component master (verified via step8b_diagnose_deep.py).
When formula='', HRMS evaluates the row to 0 and `remove_if_zero_valued`
strips it from the slip -- which is why all 216 slips have gross_pay=0.

Fix
---
SQL UPDATE the child rows directly (the structure is submitted, so the
Document API would reject edits). Then clear the Frappe document cache
and reload to verify.

PAYE formula
------------
The Salary Component master's PAYE formula uses `(employee.rent_paid_annually
or 0)` and `(employee.designation or '')`. In HRMS's safe_eval context,
`employee` is the Employee NAME string, not the doc object. We rewrite
those to use direct field names (rent_paid_annually, designation) which
HRMS auto-injects into the eval context.

Run (DRY_RUN by default):
    SHA=<this commit>
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/$SHA/scripts/step8b_restore_formulas.py" -o /tmp/s8b_rf.py
    bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/s8b_rf.py').read())"
LIVE:
    sed -i 's/^DRY_RUN = True$/DRY_RUN = False/' /tmp/s8b_rf.py
    bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/s8b_rf.py').read())"
"""

from __future__ import annotations
import frappe


DRY_RUN = True
STRUCTURE = "Sungas Standard"


PAYE_FORMULA = (
    "(0 if max(0, gross_pay*12 - min(0.20 * (rent_paid_annually or 0), 500000) - (PEN_EE or 0) * 12) <= 800000 "
    "else (max(0, gross_pay*12 - min(0.20 * (rent_paid_annually or 0), 500000) - (PEN_EE or 0) * 12) - 800000) * 0.15 "
    "if max(0, gross_pay*12 - min(0.20 * (rent_paid_annually or 0), 500000) - (PEN_EE or 0) * 12) <= 3000000 "
    "else 330000 + (max(0, gross_pay*12 - min(0.20 * (rent_paid_annually or 0), 500000) - (PEN_EE or 0) * 12) - 3000000) * 0.18 "
    "if max(0, gross_pay*12 - min(0.20 * (rent_paid_annually or 0), 500000) - (PEN_EE or 0) * 12) <= 12000000 "
    "else 1950000 + (max(0, gross_pay*12 - min(0.20 * (rent_paid_annually or 0), 500000) - (PEN_EE or 0) * 12) - 12000000) * 0.21 "
    "if max(0, gross_pay*12 - min(0.20 * (rent_paid_annually or 0), 500000) - (PEN_EE or 0) * 12) <= 25000000 "
    "else 4680000 + (max(0, gross_pay*12 - min(0.20 * (rent_paid_annually or 0), 500000) - (PEN_EE or 0) * 12) - 25000000) * 0.23 "
    "if max(0, gross_pay*12 - min(0.20 * (rent_paid_annually or 0), 500000) - (PEN_EE or 0) * 12) <= 50000000 "
    "else 10430000 + (max(0, gross_pay*12 - min(0.20 * (rent_paid_annually or 0), 500000) - (PEN_EE or 0) * 12) - 50000000) * 0.25"
    ") / 12"
)

PAYE_CONDITION = (
    "(designation or '').lower().strip() not in "
    "('chairman', 'non-executive director', 'non executive director', 'independent director')"
)


# Map: (parentfield, salary_component) -> (formula, condition)
# Sources of truth: Salary Component master (40/25/25/10 split, NTAA 2025).
RESTORE = {
    # ---- EARNINGS ----
    ("earnings", "Basic Pay"):                ("base * 0.40", ""),
    ("earnings", "Transport Allowance"):      ("base * 0.25", ""),
    ("earnings", "Housing Allowance"):        ("base * 0.25", ""),
    ("earnings", "Cost of Living Allowance"): ("base * 0.10", ""),
    ("earnings", "Medical Allowance"):        ("hmo_monthly_premium_company_paid or 0", ""),
    # ---- DEDUCTIONS ----
    ("deductions", "NSITF"):                  ("base * 0.01", ""),
    ("deductions", "Pension Employee"):       ("(BS + HA + TA) * 0.08", ""),
    ("deductions", "Pension Employer"):       ("(BS + HA + TA) * 0.10", ""),
    ("deductions", "PAYE"):                   (PAYE_FORMULA, PAYE_CONDITION),
    ("deductions", "HMO Top-up (Staff Paid)"):("hmo_monthly_topup_staff_paid or 0", ""),
}


def main() -> None:
    print("=" * 72)
    print(f" Restore Sungas Standard formulas  (DRY_RUN={DRY_RUN})")
    print("=" * 72)
    print()

    ss = frappe.db.get_value("Salary Structure", STRUCTURE,
                             ["docstatus", "is_active"], as_dict=True)
    if not ss:
        print(f"  ! Structure '{STRUCTURE}' not found")
        return
    print(f"  Structure: docstatus={ss['docstatus']}  is_active={ss['is_active']!r}")
    print()

    plan: list[tuple[str, str, str, str, str, str]] = []
    for (parentfield, component), (new_formula, new_condition) in RESTORE.items():
        row = frappe.db.sql("""
            select name, formula, `condition`
            from `tabSalary Detail`
            where parent = %s and parentfield = %s and salary_component = %s
        """, (STRUCTURE, parentfield, component), as_dict=True)
        if not row:
            print(f"  ! Row not found: ({parentfield}, {component})")
            continue
        cur_f = row[0]["formula"] or ""
        cur_c = row[0]["condition"] or ""
        if cur_f == new_formula and cur_c == new_condition:
            print(f"  = OK    {parentfield:<10} {component:<28} (already matches)")
            continue
        plan.append((row[0]["name"], parentfield, component, new_formula, new_condition, cur_f))
        print(f"  +PLAN  {parentfield:<10} {component:<28}")
        print(f"          OLD formula: {cur_f!r}")
        print(f"          NEW formula: {new_formula[:120]!r}{'…' if len(new_formula) > 120 else ''}")
        if new_condition:
            print(f"          NEW condition: {new_condition!r}")

    print()
    print(f"  Total rows to update: {len(plan)}")
    print()

    if DRY_RUN or not plan:
        print("  [DRY_RUN] No DB writes performed.")
        return

    # ---- LIVE: SQL UPDATE child rows ----
    for child_name, parentfield, component, formula, condition, _old in plan:
        frappe.db.sql("""
            update `tabSalary Detail`
            set formula = %s, `condition` = %s, modified = NOW()
            where name = %s
        """, (formula, condition, child_name))
    frappe.db.commit()

    # Clear caches so HRMS reads new formulas next slip create
    frappe.clear_document_cache("Salary Structure", STRUCTURE)
    print(f"  + Updated {len(plan)} rows.")

    # Verify
    print()
    print("  Verification:")
    for parentfield, comp in [(p, c) for (p, c), _ in RESTORE.items()]:
        row = frappe.db.get_value(
            "Salary Detail",
            {"parent": STRUCTURE, "parentfield": parentfield, "salary_component": comp},
            ["formula"], as_dict=True,
        )
        if row:
            f = (row["formula"] or "")[:70]
            ok = "OK" if row["formula"] else "EMPTY"
            print(f"    {ok:<5} {parentfield:<10} {comp:<28} formula={f!r}")


# bench execute scope-fix
try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
