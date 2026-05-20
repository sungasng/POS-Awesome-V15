"""
Dump proposed Grade Level mapping for HR review BEFORE running step4a live.

Output: /tmp/grade_mapping_for_hr.csv

Columns:
  employee_id, employee_name, designation, department, branch,
  proposed_grade, mapping_source

Where `mapping_source` is:
  'auto'    -> matched via DESIGNATION_GRADE_OVERRIDES
  'default' -> no match, defaulted to G6 (HR must review)

HR action: open the CSV, override any row's `proposed_grade` column,
re-save as /tmp/grade_overrides.csv, then run apply_grade_overrides.py.

Run:
    curl -fsSL "<raw url>/scripts/dump_grade_mapping.py" -o /tmp/dump.py
    bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/dump.py').read())"
    # then SCP /tmp/grade_mapping_for_hr.csv off the bench
"""

from __future__ import annotations
import csv
from pathlib import Path
import frappe


# Mirror the mapping from step4a (keep in sync if you edit step4a)
DESIGNATION_GRADE_OVERRIDES = {
    # G1 - Senior Management / Executive Directors
    "Chief Operating Officer": "G1",
    "Chief Executive Officer": "G1",
    "Managing Director":       "G1",
    "Executive Director":      "G1",
    # G2 - Senior Management / Heads of Strategy
    "Head of Sales & Marketing":   "G2",
    "Head of Sales and Marketing": "G2",
    "Head of Finance":             "G2",
    "Head of Operations":          "G2",
    "Head of Internal Control":    "G2",
    "Head of HR":                  "G2",
    "Head of Procurement":         "G2",
    "Finance Manager":             "G2",
    "Operations Manager":          "G2",
    # G3 - Middle Management / Heads of Units
    "Plant Manager":           "G3",
    "A.g Plant Manager":       "G3",
    "Accountant":              "G3",
    "Internal Control Officer": "G3",
    # G4 - Junior Management / Unit Backups
    "Platform Supervisor": "G4",
    "Plant Supervisor":    "G4",
    "Supervisor":          "G4",
    # G5 - Officers / SMEs
    "Account Officer":            "G5",
    "Account Receivable Officer": "G5",
    "HR Officer":                 "G5",
    "Sales Executive":            "G5",
    "Commercial Sales Executive": "G5",
    "Procurement Officer":        "G5",
    "Security Coordinator":       "G5",
}

GRADE_LABEL = {
    "G1": "G1 - Exec Dir",
    "G2": "G2 - Senior Mgmt",
    "G3": "G3 - Middle Mgmt",
    "G4": "G4 - Junior Mgmt",
    "G5": "G5 - Officers",
    "G6": "G6 - Junior Staff",
    "G7": "G7 - Junior Staff",
}


def main():
    employees = frappe.db.sql("""
        select name, employee_name, designation, department, branch, date_of_joining
        from tabEmployee
        where status='Active'
        order by employee_name
    """, as_dict=1)

    print(f"Dumping {len(employees)} active employees...")

    out_path = Path("/tmp/grade_mapping_for_hr.csv")
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "employee_id", "employee_name", "designation", "department",
            "branch", "date_of_joining", "proposed_grade", "grade_description",
            "mapping_source",
        ])
        counts = {"auto": 0, "default": 0}
        by_grade = {g: 0 for g in GRADE_LABEL}
        for emp in employees:
            desig = (emp.get("designation") or "").strip()
            grade = DESIGNATION_GRADE_OVERRIDES.get(desig)
            source = "auto" if grade else "default"
            if not grade:
                grade = "G6"
            counts[source] += 1
            by_grade[grade] += 1
            w.writerow([
                emp["name"],
                emp["employee_name"],
                desig,
                emp.get("department") or "",
                emp.get("branch") or "",
                str(emp.get("date_of_joining") or ""),
                grade,
                GRADE_LABEL[grade],
                source,
            ])

    print(f"\n[OK] wrote {out_path}\n")
    print(f"Total employees:    {len(employees)}")
    print(f"  Auto-mapped:      {counts['auto']}")
    print(f"  Defaulted to G6:  {counts['default']}")
    print()
    print("Distribution:")
    for g in sorted(by_grade):
        print(f"  {GRADE_LABEL[g]:25s} {by_grade[g]:4d}")
    print()
    print("Download command (run locally):")
    print("  scp frappe@<bench>:/tmp/grade_mapping_for_hr.csv ./")


try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
