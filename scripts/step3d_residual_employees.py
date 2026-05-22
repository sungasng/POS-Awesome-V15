"""
Phase 6 / Step 3d: Residual employee onboarding (HR confirmation 2026-05).

Resolves the 4 names HR confirmed on 2026-05-22:

  1. DOMINION ROLAND       -- already on ERP (HR-EMP-00326). Verify only.
  2. BULUS SATI            -- already on ERP (HR-EMP-00327). Verify only.
  3. ISAAC ONWUZULUIGBO    -- NEW HIRE. Hire date 2026-03-08. Onboard.
  4. GODWIN SAVIOUR        -- NEW HIRE. Hire date 2026-02-02. Onboard.

For #1/#2 the script just confirms the records are active, on the right
salary structure (Sungas Standard), and have an active SSA + bank details.

For #3/#4 the script creates the Employee (idempotent on duplicates) with the
HR-supplied bank/NIN/DOB. The remaining onboarding fields (designation,
department, branch, salary base, grade) MUST be filled in the NEW_HIRES list
below before LIVE run -- the script will refuse to insert a record while any
required field is left as `None`.

DRY_RUN=True   -> prints what would change. No DB writes.
DRY_RUN=False  -> persists records.

Run:
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/feat/sungas-customizations/scripts/step3d_residual_employees.py" -o /tmp/s3d.py
    bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/s3d.py').read())"
"""

from __future__ import annotations
from pathlib import Path
import frappe


DRY_RUN = True

COMPANY            = "SUNGAS COMPANY LIMITED"
DEFAULT_STRUCTURE  = "Sungas Standard"
RENT_RELIEF_FLOOR  = 2_500_000   # so PAYE relief caps at 500,000

# --- Existing records to verify ----------------------------------------------
# (HR thought these were on ERP but they aren't -- moved to NEW_HIRES below.)
EXISTING: list[dict] = []

# --- New hires to onboard ----------------------------------------------------
# Fill every `None` below before flipping DRY_RUN=False.
NEW_HIRES = [
    {
        # ---- HR-supplied (full) ----
        "first_name":      "Isaac",
        "last_name":       "Onwuzuluigbo",
        "employee_name":   "ISAAC ONWUZULUIGBO",
        "date_of_birth":   "1995-08-06",
        "date_of_joining": "2026-03-08",
        "ndlea_nin":       "96889401898",
        "bank_name":       "Sterling Bank",
        "bank_ac_no":      "942720863",
        "gender":              "Male",
        "designation":         "Filler",
        "department":          "Operations - SCL",
        "branch":              "Okhuoromi",
        "payroll_cost_center": "Okhuoromi",
        "grade_level":         "G7",
        "salary_base":         78078,
        "eligible_for_13th_month": 0,
    },
    {
        # ---- HR-supplied (full) ----
        "first_name":      "Godwin",
        "last_name":       "Saviour",
        "employee_name":   "GODWIN SAVIOUR",
        "date_of_birth":   "2000-07-24",
        "date_of_joining": "2026-02-02",
        "ndlea_nin":       "26115119179",
        "bank_name":       "United Bank for Africa",
        "bank_ac_no":      "2314285751",
        "gender":              "Male",
        "designation":         "Rider",
        "department":          "Logistics",
        "branch":              "Okhuoromi",
        "payroll_cost_center": "Okhuoromi",
        "grade_level":         "G6",
        "salary_base":         105287,
        "eligible_for_13th_month": 0,
    },
    {
        # ---- Dominion Roland (HR thought he was HR-EMP-00326, he isn't) ----
        "first_name":      "Dominion",
        "last_name":       "Roland",
        "employee_name":   "DOMINION ROLAND",
        "designation":         "Cashier",
        "department":          "Operations - SCL",
        "branch":              "Okhuoromi",
        "payroll_cost_center": "Okhuoromi",
        "salary_base":         99372,
        # ---- HR confirmation 2026-05 ----
        "gender":              "Male",
        "grade_level":         "G7",
        "bank_name":           "Access Bank",
        "bank_ac_no":          "1947919792",
        # ---- Optional / pending HR ----
        "date_of_birth":   None,
        "date_of_joining": "2026-02-01",   # placeholder; HR confirms
        "ndlea_nin":       None,
        "eligible_for_13th_month": 0,
    },
    {
        # ---- Bulus Sati (HR thought he was HR-EMP-00327, he isn't) ----
        "first_name":      "Bulus",
        "last_name":       "Sati",
        "employee_name":   "BULUS SATI",
        "designation":         "Rider",
        "department":          "Logistics",
        "branch":              "Okhuoromi",
        "payroll_cost_center": "Okhuoromi",
        "salary_base":         105287,
        # ---- HR confirmation 2026-05 ----
        "gender":              "Male",
        "grade_level":         "G6",
        "bank_name":           "United Bank for Africa",
        "bank_ac_no":          "2311657009",
        # ---- Optional / pending HR ----
        "date_of_birth":   None,
        "date_of_joining": "2026-02-01",
        "ndlea_nin":       None,
        "eligible_for_13th_month": 0,
    },
]


# ---------- Helpers ----------
def _is_meta_field(doctype: str, fieldname: str) -> bool:
    try:
        return bool(frappe.get_meta(doctype).has_field(fieldname))
    except Exception:
        return False


def _resolve_cost_center(name: str, report: list[str]) -> str | None:
    """Look up an existing Cost Center matching `name` (no auto-create).

    Tries exact match, then `<name> - SCL`, then a fuzzy LIKE search on both
    `name` and `cost_center_name`. Returns the canonical ERP name or None
    if nothing matches.
    """
    if frappe.db.exists("Cost Center", name):
        return name
    candidate = f"{name} - SCL"
    if frappe.db.exists("Cost Center", candidate):
        return candidate
    by_name = frappe.db.get_value("Cost Center", {"cost_center_name": name, "company": COMPANY}, "name")
    if by_name:
        return by_name
    # Fuzzy LIKE search
    matches = frappe.db.sql("""
        select name
        from `tabCost Center`
        where company = %s
          and is_group = 0
          and disabled = 0
          and (name like %s or cost_center_name like %s)
        order by name
    """, (COMPANY, f"%{name}%", f"%{name}%"), as_dict=True)
    if len(matches) == 1:
        report.append(f"  ~ resolved Cost Center `{name}` -> `{matches[0]['name']}` (fuzzy match)")
        return matches[0]["name"]
    if len(matches) > 1:
        names = ", ".join(m["name"] for m in matches[:6])
        report.append(f"  ! Cost Center `{name}` ambiguous -- matched: {names}")
        report.append("     Edit NEW_HIRES to use the exact ERP name from that list.")
    return None


def _resolve_department(name: str, report: list[str]) -> str | None:
    if frappe.db.exists("Department", name):
        return name
    candidate = f"{name} - SCL"
    if frappe.db.exists("Department", candidate):
        return candidate
    by_name = frappe.db.get_value("Department", {"department_name": name}, "name")
    if by_name:
        return by_name
    matches = frappe.db.sql("""
        select name
        from `tabDepartment`
        where disabled = 0
          and (name like %s or department_name like %s)
        order by name
    """, (f"%{name}%", f"%{name}%"), as_dict=True)
    if len(matches) == 1:
        report.append(f"  ~ resolved Department `{name}` -> `{matches[0]['name']}` (fuzzy match)")
        return matches[0]["name"]
    if len(matches) > 1:
        names = ", ".join(m["name"] for m in matches[:6])
        report.append(f"  ! Department `{name}` ambiguous -- matched: {names}")
        report.append("     Edit NEW_HIRES to use the exact ERP name from that list.")
    return None


def ensure_masters(report: list[str]) -> None:
    """Walk NEW_HIRES, resolve CC + Department references against ERP.
    Does NOT auto-create masters -- only renames hire dict to canonical IDs."""
    report.append("## 2a. Master records (resolve, no auto-create)")
    report.append("")
    for hire in NEW_HIRES:
        cc = hire.get("payroll_cost_center")
        if cc:
            resolved = _resolve_cost_center(cc, report)
            if resolved and resolved != cc:
                hire["payroll_cost_center"] = resolved
            elif resolved is None:
                report.append(f"  ! `{hire['employee_name']}` -- Cost Center `{cc}` not found")
        dept = hire.get("department")
        if dept:
            resolved = _resolve_department(dept, report)
            if resolved and resolved != dept:
                hire["department"] = resolved
            elif resolved is None:
                report.append(f"  ! `{hire['employee_name']}` -- Department `{dept}` not found")
    report.append("")


def verify_existing(report: list[str]) -> int:
    report.append("## 1. Existing records (verify only)")
    report.append("")
    issues = 0
    for spec in EXISTING:
        emp = frappe.db.get_value(
            "Employee", spec["name"],
            ["name", "employee_name", "status", "designation", "department",
             "branch", "payroll_cost_center", "bank_name", "bank_ac_no",
             "rent_paid_annually"],
            as_dict=True,
        )
        if not emp:
            report.append(f"  ! `{spec['name']}` NOT FOUND on ERP")
            issues += 1
            continue
        if spec["expected_name_contains"].upper() not in (emp["employee_name"] or "").upper():
            report.append(f"  ! `{emp['name']}` name = {emp['employee_name']!r} "
                          f"(expected to contain {spec['expected_name_contains']!r})")
            issues += 1
        if emp["status"] != "Active":
            report.append(f"  ! `{emp['name']}` status={emp['status']!r}")
            issues += 1
        # Has active SSA?
        ssa = frappe.db.get_value(
            "Salary Structure Assignment",
            {"employee": emp["name"], "docstatus": 1},
            ["name", "salary_structure", "base", "from_date"],
            as_dict=True,
        )
        if not ssa:
            report.append(f"  ! `{emp['name']}` has NO active SSA -- create one before payroll")
            issues += 1
        else:
            report.append(f"  = `{emp['name']}` {emp['employee_name']} | "
                          f"SSA {ssa['name']} on {ssa['salary_structure']} "
                          f"(base NGN {float(ssa['base'] or 0):,.0f}, from {ssa['from_date']})")
        # Bank details + rent
        if not (emp["bank_name"] and emp["bank_ac_no"]):
            report.append("    ! Missing bank_name/bank_ac_no")
            issues += 1
        rent = float(emp.get("rent_paid_annually") or 0)
        if rent < RENT_RELIEF_FLOOR:
            report.append(f"    ~ rent_paid_annually = {rent:,.0f} (Step 3c will floor to {RENT_RELIEF_FLOOR:,.0f})")
    report.append("")
    return issues


def find_pending_fields(hire: dict) -> list[str]:
    required = ["gender", "designation", "department", "branch",
                "payroll_cost_center", "grade_level", "salary_base"]
    return [f for f in required if hire.get(f) is None]


def find_missing_masters(hire: dict) -> list[str]:
    """Return a human-readable list of master records that don't exist."""
    missing = []
    if hire.get("branch") and not frappe.db.exists("Branch", hire["branch"]):
        missing.append(f"Branch `{hire['branch']}`")
    if hire.get("department") and not frappe.db.exists("Department", hire["department"]):
        # ERPNext sometimes suffixes department with " - <abbr>"
        if not frappe.db.exists("Department", {"department_name": hire["department"]}):
            missing.append(f"Department `{hire['department']}`")
    if hire.get("payroll_cost_center") and not frappe.db.exists("Cost Center", hire["payroll_cost_center"]):
        # try with company suffix
        for guess in (f"{hire['payroll_cost_center']} - SCL",):
            if frappe.db.exists("Cost Center", guess):
                hire["payroll_cost_center"] = guess  # auto-correct
                break
        else:
            missing.append(f"Cost Center `{hire['payroll_cost_center']}` (or `... - SCL`)")
    if hire.get("designation") and not frappe.db.exists("Designation", hire["designation"]):
        missing.append(f"Designation `{hire['designation']}`")
    if hire.get("bank_name") and not frappe.db.exists("Bank", hire["bank_name"]):
        missing.append(f"Bank `{hire['bank_name']}`")
    return missing


def upsert_new_hire(hire: dict, report: list[str]) -> str | None:
    """Insert Employee + active SSA. Returns the Employee.name or None."""
    name_query = frappe.db.get_value(
        "Employee",
        {"employee_name": hire["employee_name"]},
        "name",
    )
    if name_query:
        report.append(f"  = `{hire['employee_name']}` already exists as `{name_query}` -- skipping insert")
        return name_query

    pending = find_pending_fields(hire)
    if pending:
        report.append(f"  ! `{hire['employee_name']}` -- missing: {', '.join(pending)}")
        report.append("     (fill these in NEW_HIRES list, then re-run)")
        return None

    missing_masters = find_missing_masters(hire)
    if missing_masters:
        report.append(f"  ! `{hire['employee_name']}` -- master records missing on ERP:")
        for m in missing_masters:
            report.append(f"      - {m}")
        report.append("     (HR must create these masters first OR correct the value in NEW_HIRES)")
        return None

    if DRY_RUN:
        report.append(f"  + would-create Employee `{hire['employee_name']}` "
                      f"(joined {hire['date_of_joining']}, branch {hire['branch']})")
        return None

    # Build Employee doc
    # Build Employee doc (skip None-valued optional fields so Frappe doesn't reject them)
    doc_data = {
        "doctype": "Employee",
        "first_name": hire["first_name"],
        "last_name":  hire["last_name"],
        "employee_name": hire["employee_name"],
        "date_of_joining": hire["date_of_joining"],
        "gender":          hire["gender"],
        "status":          "Active",
        "company":         COMPANY,
        "designation":     hire["designation"],
        "department":      hire["department"],
        "branch":          hire["branch"],
    }
    for opt in ("date_of_birth", "bank_name", "bank_ac_no"):
        if hire.get(opt):
            doc_data[opt] = hire[opt]
    doc = frappe.get_doc(doc_data)
    # Custom fields (only if present in this site's schema)
    if _is_meta_field("Employee", "payroll_cost_center"):
        doc.payroll_cost_center = hire["payroll_cost_center"]
    if _is_meta_field("Employee", "grade_level"):
        doc.grade_level = hire["grade_level"]
    if _is_meta_field("Employee", "rent_paid_annually"):
        doc.rent_paid_annually = RENT_RELIEF_FLOOR
    if _is_meta_field("Employee", "eligible_for_13th_month"):
        doc.eligible_for_13th_month = int(hire.get("eligible_for_13th_month") or 0)
    if _is_meta_field("Employee", "ndlea_nin") and hire.get("ndlea_nin"):
        doc.ndlea_nin = hire["ndlea_nin"]

    doc.insert(ignore_permissions=True)

    # Active SSA from join date
    ssa = frappe.get_doc({
        "doctype": "Salary Structure Assignment",
        "employee": doc.name,
        "salary_structure": DEFAULT_STRUCTURE,
        "from_date": hire["date_of_joining"],
        "base": float(hire["salary_base"]),
        "company": COMPANY,
    })
    ssa.insert(ignore_permissions=True)
    ssa.submit()
    frappe.db.commit()

    report.append(f"  + created `{doc.name}` ({doc.employee_name}) + SSA `{ssa.name}` "
                  f"on `{DEFAULT_STRUCTURE}` (base NGN {float(hire['salary_base']):,.0f})")
    return doc.name


def main():
    print("=" * 72)
    print(f" Phase 6 / Step 3d -- Residual Employees (DRY_RUN={DRY_RUN})")
    print("=" * 72)

    report: list[str] = []
    report.append(f"# Step 3d -- Residual Employees (DRY_RUN={DRY_RUN})")
    report.append("")
    report.append(f"_Generated: {frappe.utils.now_datetime()} | Site: {frappe.local.site}_")
    report.append("")

    issues = verify_existing(report)

    ensure_masters(report)

    report.append("## 2. New hires (onboard)")
    report.append("")
    inserted = 0
    blocked = 0
    for hire in NEW_HIRES:
        result = upsert_new_hire(hire, report)
        if result and not DRY_RUN:
            inserted += 1
        elif find_pending_fields(hire):
            blocked += 1

    report.append("")
    report.append("## Summary")
    report.append("")
    report.append(f"  Existing-record issues : {issues}")
    report.append(f"  New hires inserted     : {inserted}")
    report.append(f"  New hires blocked      : {blocked} (missing required fields)")

    p = Path("/tmp/step3d_residual_employees.md")
    p.write_text("\n".join(report), encoding="utf-8")
    print()
    for line in report:
        print(line)
    print()
    print(f"[OK] {p}")
    if DRY_RUN:
        print()
        print("[DRY_RUN] Nothing was written. Fill missing fields, set DRY_RUN=False, and re-run.")


try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
