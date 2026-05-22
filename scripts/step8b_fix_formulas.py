"""
Phase 6 / Step 8b-FIX-FORMULAS: rewrite Sungas Standard rows 6 + 7 formulas
to use ERPNext's salary-slip eval context correctly.

Problem
-------
The current formulas reference `employee.grade_level` and
`employee.date_of_joining`. In ERPNext's Salary Slip safe_eval context,
`employee` is the Employee.name STRING, not an object -- so attribute access
fails with: `'str' object has no attribute 'grade_level'`.

Employee field values are auto-injected as TOP-LEVEL names. Also: `BS` is
not a defined abbreviation; use `base` (the SSA base).

Fixes
-----
Row 6 (Leave Allowance):
  OLD: (0.10 * BS * 12) if (employee.grade_level and employee.date_of_joining
       and getdate(start_date).month == getdate(employee.date_of_joining).month
       and date_diff(start_date, employee.date_of_joining) >= 365) else 0
  NEW: (0.10 * base * 12) if (grade_level and date_of_joining
       and getdate(start_date).month == getdate(date_of_joining).month
       and date_diff(start_date, date_of_joining) >= 365) else 0

Row 7 (13th Month):
  OLD: BS if (employee.eligible_for_13th_month and employee.grade_level
       and getdate(start_date).month == 12 and employee.date_of_joining
       and date_diff(start_date, employee.date_of_joining) >= 365
       and getdate(employee.date_of_joining).month < 8) else 0
  NEW: base if (eligible_for_13th_month and grade_level
       and getdate(start_date).month == 12 and date_of_joining
       and date_diff(start_date, date_of_joining) >= 365
       and getdate(date_of_joining).month < 8) else 0

Idempotent: skips rows already fixed.

Run:
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/feat/sungas-customizations/scripts/step8b_fix_formulas.py" -o /tmp/s8b_ff.py
    bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/s8b_ff.py').read())"
"""

from __future__ import annotations
import frappe


DRY_RUN = True

STRUCTURE = "Sungas Standard"

NEW_FORMULAS = {
    "Leave Allowance": (
        "(0.10 * base * 12) if (grade_level and date_of_joining "
        "and getdate(start_date).month == getdate(date_of_joining).month "
        "and date_diff(start_date, date_of_joining) >= 365) else 0"
    ),
    "13th Month": (
        "base if (eligible_for_13th_month and grade_level "
        "and getdate(start_date).month == 12 and date_of_joining "
        "and date_diff(start_date, date_of_joining) >= 365 "
        "and getdate(date_of_joining).month < 8) else 0"
    ),
}


def main():
    print("=" * 72)
    print(f" Phase 6 / Step 8b -- Fix formulas (DRY_RUN={DRY_RUN})")
    print("=" * 72)

    ss = frappe.get_doc("Salary Structure", STRUCTURE)
    changed = 0
    for row in ss.earnings:
        target = NEW_FORMULAS.get(row.salary_component)
        if not target:
            continue
        if (row.formula or "").strip() == target:
            print(f"  = `{row.salary_component}` already at target formula")
            continue
        print(f"  + updating `{row.salary_component}` (row {row.idx})")
        if not DRY_RUN:
            row.formula = target
        changed += 1

    if DRY_RUN:
        print()
        print(f"[DRY_RUN] Would update {changed} rows. Set DRY_RUN=False and re-run.")
        return

    if changed:
        ss.save(ignore_permissions=True)
        frappe.db.commit()
        print(f"  [OK] Updated {changed} rows on `{STRUCTURE}`")
    else:
        print("  Nothing to update.")


try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
