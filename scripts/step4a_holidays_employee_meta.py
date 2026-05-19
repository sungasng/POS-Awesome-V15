"""
Phase 6 / Step 4a: Holiday Lists + employee metadata fields.

Sections:
  1. Custom field Employee.grade_level (Select G1-G7, default G6)
  2. Custom field Employee.eligible_for_13th_month (Check, default 1)
  3. Holiday List 'Sungas HQ Holidays 2026' (Mon-Fri, Sat+Sun weekly off)
  4. Holiday List 'Sungas Outlets Holidays 2026' (7-day shift, no weekly off)
  5. Assign Holiday List per employee based on branch (Headquarters -> HQ list,
     everyone else -> Outlets list)

NOTE on grade defaults: All 217 employees default to G6. HR should override
high-grade staff via UI or by adding mappings in DESIGNATION_GRADE_OVERRIDES
below and re-running. Mapping is conservative (catches the obvious senior
roles); HR has final say.

Toggle DRY_RUN=True to preview.

Run:
    curl -fsSL "<raw url>/scripts/step4a_holidays_employee_meta.py" -o /tmp/s4a.py
    bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/s4a.py').read())"
"""

from __future__ import annotations
from pathlib import Path
import frappe


DRY_RUN = False


# 2026 Nigerian Federal Public Holidays
HOLIDAYS_2026 = [
    ("2026-01-01", "New Year's Day"),
    ("2026-03-20", "Eid el-Fitr Day 1"),       # subject to moon sighting
    ("2026-03-21", "Eid el-Fitr Day 2"),       # subject to moon sighting
    ("2026-04-03", "Good Friday"),
    ("2026-04-06", "Easter Monday"),
    ("2026-05-01", "Workers' Day"),
    ("2026-05-27", "Eid el-Kabir Day 1"),      # subject to moon sighting
    ("2026-05-28", "Eid el-Kabir Day 2"),      # subject to moon sighting
    ("2026-06-12", "Democracy Day"),
    ("2026-08-25", "Mawlid an-Nabi"),           # subject to moon sighting
    ("2026-10-01", "Independence Day"),
    ("2026-12-25", "Christmas Day"),
    ("2026-12-26", "Boxing Day"),
]

# Designation -> Grade Level overrides (conservative mapping).
# Anything NOT matched defaults to G6. HR adjusts via UI post-run.
DESIGNATION_GRADE_OVERRIDES = {
    # G1 - Senior Management / Executive Directors
    "Chief Operating Officer": "G1",
    "Chief Executive Officer": "G1",
    "Managing Director":       "G1",
    "Executive Director":      "G1",
    # G2 - Senior Management / Heads of Strategy
    "Head of Sales & Marketing":  "G2",
    "Head of Sales and Marketing":"G2",
    "Head of Finance":             "G2",
    "Head of Operations":          "G2",
    "Head of Internal Control":    "G2",
    "Head of HR":                  "G2",
    "Head of Procurement":         "G2",
    "Finance Manager":             "G2",
    "Operations Manager":          "G2",
    # G3 - Middle Management / Heads of Units
    "Plant Manager":          "G3",
    "A.g Plant Manager":      "G3",
    "Accountant":             "G3",
    "Internal Control Officer":"G3",
    # G4 - Junior Management / Unit Backups
    "Platform Supervisor":  "G4",
    "Plant Supervisor":     "G4",
    "Supervisor":           "G4",
    # G5 - Officers / SMEs
    "Account Officer":           "G5",
    "Account Receivable Officer":"G5",
    "HR Officer":                "G5",
    "Sales Executive":           "G5",
    "Commercial Sales Executive":"G5",
    "Procurement Officer":       "G5",
    "Security Coordinator":      "G5",
    # G6/G7 - default (Junior Staff)
    # Cashier, Filler, Driver, Cleaner, Bobtail Driver, Tricycle Rider, etc.
}


def add_grade_field(report: list[str]) -> None:
    report.append("## 1. Custom field Employee.grade_level")
    report.append("")
    cf_name = "Employee-grade_level"
    if frappe.db.exists("Custom Field", cf_name):
        report.append("  = already exists")
        report.append("")
        return
    if DRY_RUN:
        report.append("  + would-insert (Select, default=G6)")
        report.append("")
        return
    frappe.get_doc({
        "doctype": "Custom Field",
        "dt": "Employee",
        "fieldname": "grade_level",
        "label": "Grade Level",
        "fieldtype": "Select",
        "options": "G1\nG2\nG3\nG4\nG5\nG6\nG7",
        "default": "G6",
        "insert_after": "department",
        "description": (
            "Sungas Grade: G1=Exec Dir, G2=Snr Mgmt, G3=Middle Mgmt, "
            "G4=Junior Mgmt, G5=Officers, G6=Junior Staff, G7=Junior Staff. "
            "Drives Annual Leave entitlement (G1=20, G2=15, G3-G7=10 working days)."
        ),
    }).insert(ignore_permissions=True, ignore_if_duplicate=True)
    report.append("  + inserted")
    report.append("")


def add_13th_month_eligibility_field(report: list[str]) -> None:
    report.append("## 2. Custom field Employee.eligible_for_13th_month")
    report.append("")
    cf_name = "Employee-eligible_for_13th_month"
    if frappe.db.exists("Custom Field", cf_name):
        report.append("  = already exists")
        report.append("")
        return
    if DRY_RUN:
        report.append("  + would-insert (Check, default=1)")
        report.append("")
        return
    frappe.get_doc({
        "doctype": "Custom Field",
        "dt": "Employee",
        "fieldname": "eligible_for_13th_month",
        "label": "Eligible for 13th Month",
        "fieldtype": "Check",
        "default": "1",
        "insert_after": "grade_level",
        "description": (
            "Master toggle: pays out 1x basic salary in December for staff with "
            ">= 12 months continuous service hired before Aug 1. Management may "
            "uncheck globally (via /scripts/toggle_13th_month.py) or per-employee."
        ),
    }).insert(ignore_permissions=True, ignore_if_duplicate=True)
    report.append("  + inserted")
    report.append("")


def populate_grade_level(report: list[str]) -> None:
    report.append("## 3. Populate Employee.grade_level from designation overrides")
    report.append("")
    employees = frappe.get_all(
        "Employee",
        filters={"status": "Active"},
        fields=["name", "employee_name", "designation"],
    )
    updates = {}
    for emp in employees:
        grade = DESIGNATION_GRADE_OVERRIDES.get((emp.get("designation") or "").strip())
        if grade:
            updates[emp["name"]] = (grade, emp["employee_name"], emp.get("designation"))
    report.append(f"  Matched {len(updates)} / {len(employees)} via designation overrides.")
    report.append("  Remaining (unmatched) default to G6.")
    report.append("")

    # Sample
    if updates:
        sample_by_grade: dict[str, list] = {}
        for emp_id, (g, ename, desig) in updates.items():
            sample_by_grade.setdefault(g, []).append((emp_id, ename, desig))
        report.append("  Distribution:")
        for g in sorted(sample_by_grade):
            n = len(sample_by_grade[g])
            report.append(f"    {g}: {n} employee(s)")
            for emp_id, ename, desig in sample_by_grade[g][:3]:
                report.append(f"      - {emp_id}  {ename:35s}  desig={desig!r}")
            if n > 3:
                report.append(f"      ... and {n-3} more")
        report.append("")

    if DRY_RUN:
        report.append("  (DRY_RUN -- no updates persisted)")
        report.append("")
        return
    for emp_id, (grade, _, _) in updates.items():
        if frappe.db.get_value("Employee", emp_id, "grade_level") != grade:
            frappe.db.set_value("Employee", emp_id, "grade_level", grade)
    # Default any with NULL grade to G6
    null_employees = frappe.db.sql(
        "select name from tabEmployee where status='Active' and (grade_level is null or grade_level='')",
        as_dict=1,
    )
    for row in null_employees:
        frappe.db.set_value("Employee", row["name"], "grade_level", "G6")
    report.append(f"  + persisted {len(updates)} grade-overrides, {len(null_employees)} defaulted to G6")
    report.append("")


def ensure_holiday_list(name: str, weekly_off_days: list[str], report: list[str]) -> str | None:
    if frappe.db.exists("Holiday List", name):
        report.append(f"  = `{name}` already exists -- skipping rebuild")
        return name
    if DRY_RUN:
        report.append(f"  + would-create `{name}` (weekly_off={weekly_off_days})")
        return name
    doc = frappe.get_doc({
        "doctype": "Holiday List",
        "holiday_list_name": name,
        "from_date": "2026-01-01",
        "to_date": "2026-12-31",
        "weekly_off": weekly_off_days[0] if weekly_off_days else None,
        "country": "Nigeria",
    })
    # Add public holidays
    for date_str, hname in HOLIDAYS_2026:
        doc.append("holidays", {
            "holiday_date": date_str,
            "description": hname,
        })
    # Add weekly off as recurring holidays — Frappe will auto-generate based on weekly_off field
    doc.insert(ignore_permissions=True, ignore_if_duplicate=True)

    # If multiple weekly offs requested, also call get_weekly_off_dates
    # Frappe's standard Holiday List only supports a single weekly_off select. For
    # HQ (Sat+Sun), we add the second day's recurring holidays manually.
    if len(weekly_off_days) > 1:
        from datetime import date, timedelta
        second_day = weekly_off_days[1].lower()
        weekday_map = {"monday":0,"tuesday":1,"wednesday":2,"thursday":3,"friday":4,"saturday":5,"sunday":6}
        target = weekday_map[second_day]
        cur = date(2026,1,1)
        while cur <= date(2026,12,31):
            if cur.weekday() == target:
                doc.append("holidays", {"holiday_date": cur.isoformat(), "description": weekly_off_days[1], "weekly_off": 1})
            cur += timedelta(days=1)
        doc.save(ignore_permissions=True)

    return doc.name


def create_holiday_lists(report: list[str]) -> tuple[str | None, str | None]:
    report.append("## 4. Holiday Lists")
    report.append("")
    hq = ensure_holiday_list("Sungas HQ Holidays 2026", ["Sunday", "Saturday"], report)
    outlets = ensure_holiday_list("Sungas Outlets Holidays 2026", [], report)
    report.append("")
    return hq, outlets


def assign_holiday_lists(hq: str | None, outlets: str | None, report: list[str]) -> None:
    report.append("## 5. Assign Holiday List per Employee (Headquarters -> HQ, else -> Outlets)")
    report.append("")
    if not (hq and outlets):
        report.append("  ! Holiday lists not resolved -- skip")
        return
    employees = frappe.get_all(
        "Employee",
        filters={"status": "Active"},
        fields=["name", "branch", "holiday_list"],
    )
    hq_count = 0
    outlet_count = 0
    changes = 0
    for emp in employees:
        target = hq if (emp.get("branch") or "").lower() == "headquarters" else outlets
        if emp.get("branch") and emp["branch"].lower() == "headquarters":
            hq_count += 1
        else:
            outlet_count += 1
        if emp.get("holiday_list") != target:
            if not DRY_RUN:
                frappe.db.set_value("Employee", emp["name"], "holiday_list", target)
            changes += 1
    report.append(f"  HQ employees:      {hq_count}")
    report.append(f"  Outlet employees:  {outlet_count}")
    report.append(f"  Updated:           {changes}{' (DRY_RUN)' if DRY_RUN else ''}")
    report.append("")


def main():
    print("=" * 72)
    print(f" Phase 6 / Step 4a -- Holidays + Employee meta fields (DRY_RUN={DRY_RUN})")
    print("=" * 72)

    report: list[str] = []
    report.append("# Step 4a -- Holiday Lists + grade_level + 13th-month eligibility")
    report.append("")
    report.append(f"_Generated: {frappe.utils.now_datetime()} | Site: {frappe.local.site} | DRY_RUN={DRY_RUN}_")
    report.append("")

    add_grade_field(report)
    add_13th_month_eligibility_field(report)
    populate_grade_level(report)
    hq, outlets = create_holiday_lists(report)
    assign_holiday_lists(hq, outlets, report)

    if not DRY_RUN:
        frappe.db.commit()

    p = Path("/tmp/step4a_holidays.md")
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
