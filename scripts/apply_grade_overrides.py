"""
Apply HR-reviewed grade overrides from /tmp/grade_overrides.csv.

HR workflow:
  1. Run dump_grade_mapping.py -> /tmp/grade_mapping_for_hr.csv on bench.
  2. SCP it off, open in Excel/Sheets, edit `proposed_grade` column for any
     employee HR wants to override (e.g. fix mis-mapped G6 defaults).
  3. SCP back to bench as /tmp/grade_overrides.csv (same format, only
     `employee_id` and `proposed_grade` columns are read).
  4. Run this script.

Idempotent: only updates Employee.grade_level when CSV value differs.

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

    rows = []
    with p.open("r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            emp_id = (row.get("employee_id") or "").strip()
            grade = (row.get("proposed_grade") or "").strip().upper()
            if not emp_id or not grade:
                continue
            if grade not in VALID_GRADES:
                print(f"  ! Skipping {emp_id}: invalid grade {grade!r}")
                continue
            rows.append((emp_id, grade))

    print(f"Read {len(rows)} rows from {CSV_PATH}")

    updates = 0
    no_changes = 0
    missing = 0
    for emp_id, grade in rows:
        if not frappe.db.exists("Employee", emp_id):
            missing += 1
            continue
        current = frappe.db.get_value("Employee", emp_id, "grade_level")
        if current == grade:
            no_changes += 1
            continue
        if DRY_RUN:
            print(f"  ~ {emp_id}: {current!r} -> {grade!r}")
        else:
            frappe.db.set_value("Employee", emp_id, "grade_level", grade)
        updates += 1

    if not DRY_RUN:
        frappe.db.commit()

    print(f"\nUpdates {'projected' if DRY_RUN else 'applied'}: {updates}")
    print(f"No change:    {no_changes}")
    print(f"Missing:      {missing}")


try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
