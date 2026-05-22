"""
Apply HR-reviewed grade overrides from /tmp/grade_overrides.csv.

HR workflow:
  1. Run dump_grade_mapping.py -> /tmp/grade_mapping_for_hr.csv on bench.
  2. SCP it off, open in Excel/Sheets, edit `proposed_grade` column for any
     employee HR wants to override (e.g. fix mis-mapped G6 defaults).
  3. SCP back to bench as /tmp/grade_overrides.csv (same format, only
     `employee_id` and `proposed_grade` columns are read).
  4. Run this script.

Behaviour:
  - `proposed_grade` in (G1..G7) -> set Employee.grade_level
  - `proposed_grade` empty/blank -> CLEAR Employee.grade_level AND set
       Employee.eligible_for_13th_month=0 (treats employee as service
       provider; excluded from leave allocation, 13th month, leave allowance)

Idempotent: only writes when value differs.

Run:
    curl -fsSL "<raw url>/scripts/apply_grade_overrides.py" -o /tmp/apply.py
    bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/apply.py').read())"
"""

from __future__ import annotations
import csv
from pathlib import Path
import frappe


DRY_RUN = True

CSV_PATH = "/tmp/grade_overrides.csv"
VALID_GRADES = {"G1", "G2", "G3", "G4", "G5", "G6", "G7"}


def main():
    p = Path(CSV_PATH)
    if not p.exists():
        print(f"  ! Missing {CSV_PATH}. SCP the HR-reviewed CSV to this path first.")
        return

    parsed = []  # (emp_id, grade_or_None_for_clear)
    invalid = []
    with p.open("r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            emp_id = (row.get("employee_id") or "").strip()
            grade_raw = (row.get("proposed_grade") or "").strip().upper()
            if not emp_id:
                continue
            if grade_raw == "" or grade_raw in ("N/A", "NA", "NONE", "-"):
                parsed.append((emp_id, None))  # clear marker
                continue
            if grade_raw not in VALID_GRADES:
                invalid.append((emp_id, grade_raw))
                continue
            parsed.append((emp_id, grade_raw))

    print(f"Read {len(parsed)} valid rows from {CSV_PATH}")
    if invalid:
        print(f"  ! {len(invalid)} invalid grades skipped:")
        for emp_id, g in invalid[:10]:
            print(f"    {emp_id}: {g!r}")

    grade_set = 0
    grade_cleared = 0
    no_changes = 0
    missing = 0
    eligibility_changes = 0

    for emp_id, grade in parsed:
        if not frappe.db.exists("Employee", emp_id):
            missing += 1
            continue
        current_grade = frappe.db.get_value("Employee", emp_id, "grade_level")
        current_elig = frappe.db.get_value("Employee", emp_id, "eligible_for_13th_month")

        if grade is None:
            # Service provider: clear grade and disable 13th month
            if current_grade in (None, ""):
                pass
            elif DRY_RUN:
                print(f"  ~ {emp_id}: grade {current_grade!r} -> CLEARED (service provider)")
                grade_cleared += 1
            else:
                frappe.db.set_value("Employee", emp_id, "grade_level", None)
                grade_cleared += 1

            if (current_elig or 0) != 0:
                if DRY_RUN:
                    print(f"  ~ {emp_id}: eligible_for_13th_month -> 0 (service provider)")
                else:
                    frappe.db.set_value("Employee", emp_id, "eligible_for_13th_month", 0)
                eligibility_changes += 1
        else:
            if current_grade == grade:
                no_changes += 1
                continue
            if DRY_RUN:
                print(f"  ~ {emp_id}: grade {current_grade!r} -> {grade!r}")
            else:
                frappe.db.set_value("Employee", emp_id, "grade_level", grade)
            grade_set += 1

    if not DRY_RUN:
        frappe.db.commit()

    print(f"\nGrade {'projected' if DRY_RUN else 'applied'}: set={grade_set}, cleared={grade_cleared}")
    print(f"13th-month eligibility off: {eligibility_changes}")
    print(f"No change:    {no_changes}")
    print(f"Missing emp:  {missing}")


try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
