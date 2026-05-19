"""
Phase 6 / Step 2a -- Employee master backfill.

Idempotent. Safe to re-run. Toggle DRY_RUN=True to preview.

Creates / patches:
  - 10 Departments (incl. Internal Control)
  - 4 Employment Types (Freelance / Contract / Intern / Temporary)
  - ~50 Designations (normalised from payroll position strings)
  - 1 custom field: Employee.state_of_residence (Link, for PAYE/WHT routing)

Mutates:
  - 217 payroll Employees: designation + department + branch +
    payroll_cost_center + employment_type=Permanent + salary_mode
  - 20 off-payroll Employees: designation + department + employment_type +
    branch + status=Active
  - 3 Okhuoromi Employees: status=Active + branch + designation defaults
  - 1 NEW Employee: Babajide Rufus Ige (Head of Internal Control, Contract)
  - 1 rename: "Agent Itele 3rd" -> "Ismail Abdul Rahman"
  - 6 dedupes marked Status=Left (effective 2026-04-30)
  - 2 phantoms marked Status=Left (effective 2026-01-01)

Output: /tmp/step2a_diff.md

Run:
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/feat/sungas-customizations/scripts/step2a_employee_backfill.py" -o /tmp/step2a_employee_backfill.py
    bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/step2a_employee_backfill.py').read())"
"""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

import frappe


DRY_RUN = False     # flip True to preview without writes
DEFAULT_COMPANY = None   # auto-detected


# ---------------------------------------------------------------------------
# 1. Master data definitions
# ---------------------------------------------------------------------------

DEPARTMENTS = [
    "Executive",
    "Operations",
    "Logistics & Fleet",
    "Sales & Marketing",
    "Finance & Accounts",
    "HR & Admin",
    "Internal Control",
    "Customer Service",
    "Stores & Inventory",
    "Technical Services",
]

EMPLOYMENT_TYPES = ["Freelance", "Contract", "Intern", "Temporary"]

# Canonical Designation -> Department
DESIGNATION_TO_DEPT = {
    # Executive
    "Chief Operating Officer": "Executive",

    # Operations (corrected per HR)
    "Operations Manager": "Operations",
    "Filler": "Operations",
    "Cleaner": "Operations",
    "Platform Supervisor": "Operations",
    "Plant Supervisor": "Operations",
    "Operations Assistant": "Operations",
    "Operations Support": "Operations",
    "Supervisor": "Operations",
    "Vigilante": "Operations",
    "Security Coordinator": "Operations",
    "Traffic Warden": "Operations",
    "Operations Intern": "Operations",

    # Logistics & Fleet
    "Driver": "Logistics & Fleet",
    "Commercial Driver": "Logistics & Fleet",
    "Truck Driver": "Logistics & Fleet",
    "Bobtail Driver": "Logistics & Fleet",
    "Rider": "Logistics & Fleet",
    "Dispatch Rider": "Logistics & Fleet",
    "Tricycle Rider": "Logistics & Fleet",

    # Sales & Marketing (corrected per HR: Plant Manager + Fulfilment go here)
    "Plant Manager": "Sales & Marketing",
    "Head of Sales & Marketing": "Sales & Marketing",
    "Commercial Sales Executive": "Sales & Marketing",
    "Sales Executive": "Sales & Marketing",
    "Commercial Representative": "Sales & Marketing",
    "Fulfilment Officer": "Sales & Marketing",
    "Bulk Sale Fulfilment Officer": "Sales & Marketing",
    "Depot Representative": "Sales & Marketing",
    "Bobtail Representative": "Sales & Marketing",

    # Finance & Accounts (corrected: Cashier goes here)
    "Cashier": "Finance & Accounts",
    "Accountant": "Finance & Accounts",
    "Finance Manager": "Finance & Accounts",
    "Account Officer": "Finance & Accounts",
    "Account Receivable Officer": "Finance & Accounts",

    # HR & Admin
    "Head of Human Resources & Admin": "HR & Admin",
    "Secretary": "HR & Admin",

    # Internal Control (Babajide)
    "Head of Internal Control": "Internal Control",

    # Customer Service
    "Customer Care Representative": "Customer Service",
    "Contact Centre Supervisor": "Customer Service",
    "Customer Service Intern": "Customer Service",

    # Stores
    "Central Store Officer": "Stores & Inventory",
    "Stock Officer (Accessories)": "Stores & Inventory",

    # Technical Services
    "Head of Technical Unit": "Technical Services",
    "Technician": "Technical Services",
    "Welder": "Technical Services",

    # Off-payroll catch-all
    "Freelance Consultant": "Operations",
}

# Raw payroll position string (UPPERCASED) -> canonical Designation
POSITION_TO_DESIGNATION = {
    "COO": "Chief Operating Officer",
    "OPERATIONS MANAGER": "Operations Manager",
    "PLANT MANAGER": "Plant Manager",
    "A.G PLANT MANAGER": "Plant Manager",
    "FILLER": "Filler",
    "FILLER 2": "Filler",
    "FILLER I": "Filler",
    "FILLER IDOWINA": "Filler",
    "FILLER RECLAMATION": "Filler",
    "FILLER MABA": "Filler",
    "FLLER MABA": "Filler",
    "CASHIER": "Cashier",
    "CASHIER/FULFILMENT": "Cashier",
    "CASHIER/FULFIMENT": "Cashier",
    "CLEANER": "Cleaner",
    "CLEANER IJU": "Cleaner",
    "DRIVER": "Driver",
    "DRIVER IKEJA": "Driver",
    "DRIVER RECLAMATION": "Driver",
    "DRIVER (COMMERCIAL)": "Commercial Driver",
    "TRUCK DRIVER": "Truck Driver",
    "BOBTAIL DRIVER": "Bobtail Driver",
    "BOBTAIL TRUCK": "Bobtail Driver",
    "RIDER": "Rider",
    "DISPATCH RIDER": "Dispatch Rider",
    "TRICYCLE RIDER": "Tricycle Rider",
    "PLATFORM SUPERVISOR": "Platform Supervisor",
    "PLATFORM SUP": "Platform Supervisor",
    "PLANT SUPERVISOR": "Plant Supervisor",
    "PLANT SUP": "Plant Supervisor",
    "PLANT SUPERVISOR (ITELE)": "Plant Supervisor",
    "PLANT SUPERVISOR IJOKO": "Plant Supervisor",
    "TECHNICIAN": "Technician",
    "TECHNICIAN (BENIN)": "Technician",
    "TECHNICIAN (CONTRACT STAFF)": "Technician",
    "FULFILMENT OFFICER": "Fulfilment Officer",
    "DEPOT REP.": "Depot Representative",
    "CUSTOMER CARE REP": "Customer Care Representative",
    "ACCOUNT OFFICER": "Account Officer",
    "ACCOUNT RECEIVABLE": "Account Receivable Officer",
    "ACCOUNTANT": "Accountant",
    "A.G HEAD OF SALES & MARKETING": "Head of Sales & Marketing",
    "CENTRAL STORE OFFICER": "Central Store Officer",
    "HEAD, HUMAN RESOURCES & ADMIN": "Head of Human Resources & Admin",
    "FINANCE MANAGER": "Finance Manager",
    "CONTACT CENTRE SUPERVISOR": "Contact Centre Supervisor",
    "COMMERCIAL SALES EXECUTIVE": "Commercial Sales Executive",
    "SALES EXECUTIVE": "Sales Executive",
    "OPERATIONS ASSISTANT": "Operations Assistant",
    "BULK SALE FULFILMENT": "Bulk Sale Fulfilment Officer",
    "STOCK OFFICER (ACCESSORIES)": "Stock Officer (Accessories)",
    "OPERATIONS SUPPORT": "Operations Support",
    "COMMERCIAL REP": "Commercial Representative",
    "BOBTAIL REP": "Bobtail Representative",
    "SECRETARY": "Secretary",
    "HEAD TECHNICAL UNIT": "Head of Technical Unit",
    "SUPERVISOR": "Supervisor",
}

# Excel outlet -> HRMS Branch (canonical ERP spellings, verified via inventory_branches.py)
OUTLET_TO_BRANCH_HINT = {
    "HEADQUATERS": "Headquarters",
    "IKEJA": "Ikeja",
    "PEDRO": "Pedro",
    "OSHODI": "Oshodi",
    "ASEESE": "Aseese",
    "IJU-OTA": "Iju-Otta",
    "OSI-OTA": "Osi-Otta",
    "SEFU": "Sefu",
    "MABA": "Maba",
    "IJOKO": "Ijoko",
    "EBUTE": "Ebute",
    "UPPER MISSION": "Upper Mission",
    "IDOKPA": "Idokpa",
    "EKEHUAN": "Ekehuan",
    "OKHORUOMI": "Okhuoromi",
    "OKHUOROMI": "Okhuoromi",
    "IDOWINA": "Idowina",
    "ASABA": "Asaba",
    "RECLAMATION": "Reclamation",
    "ELEME": "Eleme",
    "CASH SALARY": None,
}

# Off-payroll roster: (emp_id, designation, employment_type, branch_hint)
OFF_PAYROLL_PATCH = [
    # Eleme
    ("HR-EMP-00218", "Security Coordinator", "Contract", "Eleme"),       # Sunday Isaac
    ("HR-EMP-00216", "Security Coordinator", "Contract", "Eleme"),       # Saloka Ngedo
    # Idowina
    ("HR-EMP-00222", "Vigilante",           "Contract", "Idowina"),      # Aigbusa Osarodion
    # Itele
    ("HR-EMP-00226", "Vigilante",           "Contract", "Iju-Otta"),     # Itele Vigilante (kept as position-named -- no person)
    ("HR-EMP-00223", "Platform Supervisor", "Contract", "Iju-Otta"),     # Jwankur Joshua - Bobo gas Itele platform sup
    ("HR-EMP-00227", "Cashier",             "Temporary", "Iju-Otta"),    # Adejoke Adeoye
    ("HR-EMP-00228", "Filler",              "Temporary", "Iju-Otta"),    # Favour Isaac
    # Iju-Otta
    ("HR-EMP-00219", "Vigilante",           "Contract", "Iju-Otta"),     # Fidipote Monsuru Abiola
    # Mafoluku (treat as Lagos / no branch match, default to HQ for now)
    ("HR-EMP-00230", "Vigilante",           "Contract", None),           # Tayo Bankole Afeez
    # Oworo
    ("HR-EMP-00220", "Vigilante",           "Contract", None),           # Oworo Vigilante (position-named)
    # Ijoko + Ijoko Lemode
    ("HR-EMP-00232", "Vigilante",           "Contract", "Ijoko"),        # Showunmi Olatunde (night)
    ("HR-EMP-00233", "Vigilante",           "Contract", "Ijoko"),        # Waheed Afolayan (day)
    ("HR-EMP-00235", "Cleaner",             "Temporary", "Ijoko"),       # Bamgboye Elizabeth
    # Pedro
    ("HR-EMP-00236", "Traffic Warden",      "Contract", "Pedro"),        # Seun Onoara
    # HQ / unlocated
    ("HR-EMP-00215", "Freelance Consultant","Freelance", "Headquarters"),# Smart Efangu
    ("HR-EMP-00237", "Operations Intern",   "Intern",    "Headquarters"),# Sarah Adegbuji
    ("HR-EMP-00238", "Operations Intern",   "Intern",    "Headquarters"),# Miracle Utalu
    ("HR-EMP-00239", "Filler",              "Temporary", "Headquarters"),# Anthony Stanley - Commercial van filler/Motorboy
    ("HR-EMP-00240", "Welder",              "Temporary", "Headquarters"),# Welder Michael
]

# Rename "Agent Itele 3Rd" -> "Ismail Abdul Rahman"
RENAMES = [
    {
        "id": "HR-EMP-00224",
        "old_name": "Agent Itele 3Rd",
        "new_name": "Ismail Abdul Rahman",
        "first_name": "Ismail",
        "last_name": "Abdul Rahman",
        "designation": "Customer Service Intern",
        "employment_type": "Intern",
        "branch_hint": "Iju-Otta",
    },
]

# Position-named ghosts that duplicate a real named record -> mark Left
DEDUPES_TO_ARCHIVE = [
    ("HR-EMP-00234", "Cleaner Ijoko",                "Real person: HR-EMP-00235 Bamgboye Elizabeth"),
    ("HR-EMP-00221", "Idowina Vigilante",            "Real person: HR-EMP-00222 Aigbusa Osarodion"),
    ("HR-EMP-00231", "Ijoko Lemode (Night) Vigilante","Real person: HR-EMP-00232 Showunmi Olatunde Mr"),
    ("HR-EMP-00229", "Mafoluku Vigilante",           "Real person: HR-EMP-00230 Tayo Bankole Afeez"),
    ("HR-EMP-00217", "Night Guard 1 Police",         "Real person: HR-EMP-00218 Sunday Isaac"),
    ("HR-EMP-00225", "Service Intern NYSC Customer", "Real person: HR-EMP-00224 (renamed to Ismail Abdul Rahman)"),
]

# Created-in-error phantoms (came from PAYROLL ADDITION / PAYROLL EXIT comment rows)
PHANTOMS_TO_ARCHIVE = [
    ("HR-EMP-00038", "Addition Payroll", "Created in error from Excel comment row 'PAYROLL ADDITION'"),
    ("HR-EMP-00039", "EXIT Payroll",     "Created in error from Excel comment row 'PAYROLL EXIT'"),
]

# Okhuoromi staff missing from April payroll -- best-effort defaults
OKHUOROMI_STAFF = [
    ("HR-EMP-00170", "Victor OBI",          "Plant Manager", "Okhuoromi"),
    ("HR-EMP-00171", "EFE Takpor",          "Filler",        "Okhuoromi"),  # DEFAULT -- needs HR confirm
    ("HR-EMP-00172", "Benjamin Emmanuella", "Filler",        "Okhuoromi"),  # DEFAULT -- needs HR confirm
]

# Babajide Rufus Ige (Head of Internal Control, Contract, off-payroll)
BABAJIDE = {
    "first_name": "Babajide",
    "middle_name": "Rufus",
    "last_name": "Ige",
    "employee_name": "Babajide Rufus Ige",
    "designation": "Head of Internal Control",
    "employment_type": "Contract",
    "department": "Internal Control",
    "gender": "Male",
    "date_of_joining": "2026-01-01",
    "date_of_birth": "1970-01-01",  # placeholder
    "status": "Active",
}


# ---------------------------------------------------------------------------
# 2. Small helpers
# ---------------------------------------------------------------------------

def _tokenise(name: str) -> frozenset[str]:
    return frozenset(t for t in re.split(r"[^A-Za-z]+", (name or "").upper()) if t)


def find_branch(hint: str | None) -> str | None:
    """Resolve outlet name to a real HRMS Branch (case-insensitive).
    First tries the canonical name from OUTLET_TO_BRANCH_HINT, then falls
    back to direct fuzzy match."""
    if not hint:
        return None
    # 1. Canonical remap (handles HEADQUATERS -> Headquarters)
    canon = OUTLET_TO_BRANCH_HINT.get(hint.upper(), hint)
    if canon and frappe.db.exists("Branch", canon):
        return canon
    # 2. Direct exact match
    if frappe.db.exists("Branch", hint):
        return hint
    # 3. Case-insensitive scan
    for b in frappe.get_all("Branch", fields=["name", "branch"]):
        candidate = b.get("branch") or b["name"]
        if hint.upper() == candidate.upper():
            return b["name"]
        if canon and canon.upper() == candidate.upper():
            return b["name"]
    return None


def find_cost_center(branch_or_outlet: str | None) -> str | None:
    """Best-effort: find a Cost Center whose name contains the outlet keyword."""
    if not branch_or_outlet:
        return None
    for cc in frappe.get_all("Cost Center", fields=["name"]):
        if branch_or_outlet.lower() in cc["name"].lower():
            return cc["name"]
    return None


def upsert_doc(doctype: str, name: str, fields: dict) -> tuple[str, bool]:
    """Insert if absent, otherwise patch. Returns (action, changed)."""
    if frappe.db.exists(doctype, name):
        if DRY_RUN:
            return "would-update", True
        doc = frappe.get_doc(doctype, name)
        changed = False
        for k, v in fields.items():
            if doc.get(k) != v and v is not None:
                doc.set(k, v)
                changed = True
        if changed:
            doc.save(ignore_permissions=True)
        return "updated", changed
    if DRY_RUN:
        return "would-insert", True
    doc = frappe.get_doc({"doctype": doctype, "name": name, **fields})
    doc.insert(ignore_permissions=True)
    return "inserted", True


# ---------------------------------------------------------------------------
# 3. Master-data seeding
# ---------------------------------------------------------------------------

def seed_departments(report: list[str]) -> None:
    report.append("## 1. Departments")
    report.append("")
    for name in DEPARTMENTS:
        action, changed = upsert_doc(
            "Department", name,
            {"department_name": name, "company": DEFAULT_COMPANY},
        )
        marker = "+" if action.startswith("would-insert") or action == "inserted" else ("~" if changed else "=")
        report.append(f"  {marker} {name}")
    report.append("")


def seed_employment_types(report: list[str]) -> None:
    report.append("## 2. Employment Types")
    report.append("")
    for name in EMPLOYMENT_TYPES:
        action, changed = upsert_doc(
            "Employment Type", name,
            {"employee_type_name": name},
        )
        marker = "+" if action.startswith("would-insert") or action == "inserted" else "="
        report.append(f"  {marker} {name}")
    report.append("")


def seed_designations(report: list[str]) -> None:
    report.append("## 3. Designations")
    report.append("")
    all_desig = sorted(set(DESIGNATION_TO_DEPT.keys()))
    inserted = updated = noop = 0
    for desig in all_desig:
        action, changed = upsert_doc(
            "Designation", desig,
            {"designation_name": desig},
        )
        if action == "inserted" or action == "would-insert":
            inserted += 1
        elif changed:
            updated += 1
        else:
            noop += 1
    report.append(f"  {len(all_desig)} canonical designations -- inserted={inserted}, updated={updated}, no-op={noop}")
    report.append("")


def seed_state_of_residence_field(report: list[str]) -> None:
    report.append("## 4. Custom field: Employee.state_of_residence")
    report.append("")
    name = "Employee-state_of_residence"
    if frappe.db.exists("Custom Field", name):
        report.append("  = already exists")
        report.append("")
        return
    if DRY_RUN:
        report.append("  + would-insert (DRY RUN)")
        report.append("")
        return
    frappe.get_doc({
        "doctype": "Custom Field",
        "dt": "Employee",
        "fieldname": "state_of_residence",
        "label": "State of Residence (PAYE/WHT routing)",
        "fieldtype": "Data",
        "insert_after": "branch",
        "description": "Used to route PAYE & WHT to the correct State IRS (e.g. LIRS / EIRS / DIRS).",
    }).insert(ignore_permissions=True)
    report.append("  + inserted")
    report.append("")


# ---------------------------------------------------------------------------
# 4. Employee mutations
# ---------------------------------------------------------------------------

def archive_employee(emp_id: str, note: str, effective: str = "2026-04-30") -> tuple[str, bool]:
    if not frappe.db.exists("Employee", emp_id):
        return "not-found", False
    if DRY_RUN:
        return "would-archive", True
    doc = frappe.get_doc("Employee", emp_id)
    if doc.status == "Left":
        return "already-left", False
    doc.status = "Left"
    doc.relieving_date = effective
    if doc.bio:
        doc.bio = (doc.bio or "") + f"\n[Step 2a auto-archive {frappe.utils.today()}] {note}"
    else:
        doc.bio = f"[Step 2a auto-archive {frappe.utils.today()}] {note}"
    doc.save(ignore_permissions=True)
    return "archived", True


def rename_employee(spec: dict, report: list[str]) -> None:
    emp_id = spec["id"]
    if not frappe.db.exists("Employee", emp_id):
        report.append(f"  ! {emp_id} not found, skip rename")
        return
    doc = frappe.get_doc("Employee", emp_id)
    branch = find_branch(spec.get("branch_hint"))
    dept = DESIGNATION_TO_DEPT.get(spec["designation"])
    if DRY_RUN:
        report.append(f"  ~ would-rename {emp_id}: {doc.employee_name!r} -> {spec['new_name']!r}, desig={spec['designation']}, dept={dept}, branch={branch}")
        return
    doc.first_name = spec["first_name"]
    doc.middle_name = ""
    doc.last_name = spec["last_name"]
    doc.employee_name = spec["new_name"]
    doc.designation = spec["designation"]
    doc.department = dept
    doc.employment_type = spec["employment_type"]
    if branch:
        doc.branch = branch
    doc.status = "Active"
    doc.save(ignore_permissions=True)
    report.append(f"  ~ renamed {emp_id}: {spec['old_name']!r} -> {spec['new_name']!r}")


def patch_off_payroll(report: list[str]) -> None:
    report.append("## 5. Off-payroll staff (20 records)")
    report.append("")
    for emp_id, desig, etype, branch_hint in OFF_PAYROLL_PATCH:
        if not frappe.db.exists("Employee", emp_id):
            report.append(f"  ! {emp_id} not found")
            continue
        dept = DESIGNATION_TO_DEPT.get(desig)
        branch = find_branch(branch_hint)
        patch = {
            "designation": desig,
            "department": dept,
            "employment_type": etype,
            "status": "Active",
        }
        if branch:
            patch["branch"] = branch
        if DRY_RUN:
            report.append(f"  ~ would-patch {emp_id}: desig={desig}, dept={dept}, type={etype}, branch={branch}")
            continue
        doc = frappe.get_doc("Employee", emp_id)
        for k, v in patch.items():
            if v is not None:
                doc.set(k, v)
        doc.save(ignore_permissions=True)
        report.append(f"  ~ {emp_id} {doc.employee_name}: desig={desig}, dept={dept}, type={etype}, branch={branch or '-'}")
    report.append("")


def patch_okhuoromi(report: list[str]) -> None:
    report.append("## 6. Okhuoromi staff (3 records -- defaults, awaiting HR confirm)")
    report.append("")
    for emp_id, name, desig, branch_hint in OKHUOROMI_STAFF:
        if not frappe.db.exists("Employee", emp_id):
            report.append(f"  ! {emp_id} not found")
            continue
        dept = DESIGNATION_TO_DEPT.get(desig)
        branch = find_branch(branch_hint)
        patch = {
            "designation": desig,
            "department": dept,
            "employment_type": "Contract",
            "status": "Active",
        }
        if branch:
            patch["branch"] = branch
        if DRY_RUN:
            report.append(f"  ~ would-patch {emp_id} ({name}): desig={desig}, branch={branch}")
            continue
        doc = frappe.get_doc("Employee", emp_id)
        for k, v in patch.items():
            if v is not None:
                doc.set(k, v)
        doc.save(ignore_permissions=True)
        report.append(f"  ~ {emp_id} {name}: desig={desig}, branch={branch or '-'} (DEFAULT -- HR confirmation needed)")
    report.append("")


def create_babajide(report: list[str]) -> None:
    report.append("## 7. New employee: Babajide Rufus Ige (Head of Internal Control)")
    report.append("")
    existing = frappe.get_all(
        "Employee",
        filters={"employee_name": "Babajide Rufus Ige"},
        fields=["name"],
    )
    if existing:
        report.append(f"  = already exists: {existing[0]['name']}")
        report.append("")
        return
    if DRY_RUN:
        report.append("  + would-insert (DRY RUN)")
        report.append("")
        return
    doc = frappe.get_doc({
        "doctype": "Employee",
        "company": DEFAULT_COMPANY,
        **BABAJIDE,
    })
    doc.insert(ignore_permissions=True)
    report.append(f"  + inserted: {doc.name} (Babajide Rufus Ige)")
    report.append("")


def archive_dedupes(report: list[str]) -> None:
    report.append("## 8. Dedupes -- mark position-named records as Left")
    report.append("")
    for emp_id, label, note in DEDUPES_TO_ARCHIVE:
        action, _ = archive_employee(emp_id, note, effective="2026-04-30")
        report.append(f"  - {emp_id} ({label}): {action} -- {note}")
    report.append("")


def archive_phantoms(report: list[str]) -> None:
    report.append("## 9. Phantom records -- mark Left")
    report.append("")
    for emp_id, label, note in PHANTOMS_TO_ARCHIVE:
        action, _ = archive_employee(emp_id, note, effective="2026-01-01")
        report.append(f"  - {emp_id} ({label}): {action}")
    report.append("")


def patch_payroll_staff(report: list[str]) -> None:
    """Read /tmp/_payroll_roster.py and patch the 217 matched employees."""
    sys.path.insert(0, "/tmp")
    try:
        from _payroll_roster import PAYROLL_APR_2026 as ROSTER  # type: ignore
    except Exception as exc:
        report.append(f"## 10. ABORT -- could not import /tmp/_payroll_roster.py: {exc}")
        return

    # Build index of all ERP employees by token-set
    idx = defaultdict(list)
    for emp in frappe.get_all("Employee", fields=["name", "employee_name", "status"]):
        idx[_tokenise(emp["employee_name"])].append(emp)

    report.append(f"## 10. Payroll staff backfill ({len(ROSTER)} records)")
    report.append("")
    patched = 0
    unresolved = []
    by_designation = defaultdict(int)
    by_dept = defaultdict(int)

    for row in ROSTER:
        tokens = _tokenise(row["name"])
        candidates = idx.get(tokens) or [
            c for key, cands in idx.items() for c in cands
            if tokens and (tokens <= key or key <= tokens) and len(tokens & key) >= 2
        ]
        if len(candidates) != 1:
            unresolved.append(row)
            continue
        emp = candidates[0]
        desig = POSITION_TO_DESIGNATION.get(row["position"].strip().upper())
        if not desig:
            unresolved.append({**row, "_reason": f"no designation map for {row['position']!r}"})
            continue
        dept = DESIGNATION_TO_DEPT.get(desig)
        branch = find_branch(row["outlet"]) or find_branch(OUTLET_TO_BRANCH_HINT.get(row["outlet"].upper()))
        cc = find_cost_center(OUTLET_TO_BRANCH_HINT.get(row["outlet"].upper()) or row["outlet"])

        patch = {
            "designation": desig,
            "department": dept,
            "employment_type": "Contract" if row["pay_mode"] == "Cash" else "Permanent",
            "salary_mode": "Cash" if row["pay_mode"] == "Cash" else "Bank",
        }
        if branch:
            patch["branch"] = branch
        if cc and frappe.get_meta("Employee").has_field("payroll_cost_center"):
            patch["payroll_cost_center"] = cc

        if DRY_RUN:
            patched += 1
        else:
            doc = frappe.get_doc("Employee", emp["name"])
            for k, v in patch.items():
                if v is not None:
                    doc.set(k, v)
            doc.save(ignore_permissions=True)
            patched += 1
        by_designation[desig] += 1
        by_dept[dept] += 1

    report.append(f"  - patched: **{patched}** / {len(ROSTER)}")
    report.append(f"  - unresolved: {len(unresolved)}")
    if unresolved:
        report.append("")
        report.append("  Unresolved rows:")
        for r in unresolved[:30]:
            reason = r.get("_reason", "no unique ERP match")
            report.append(f"    - {r['outlet']} | {r['name']} | {r['position']} -- {reason}")
        if len(unresolved) > 30:
            report.append(f"    ... and {len(unresolved)-30} more")
    report.append("")
    report.append("  By designation (top 10):")
    for d, n in sorted(by_designation.items(), key=lambda x: -x[1])[:10]:
        report.append(f"    {n:3d}x  {d}")
    report.append("")
    report.append("  By department:")
    for d, n in sorted(by_dept.items(), key=lambda x: -x[1]):
        report.append(f"    {n:3d}x  {d}")
    report.append("")


# ---------------------------------------------------------------------------
# 5. Driver
# ---------------------------------------------------------------------------

def detect_company() -> str | None:
    companies = frappe.get_all("Company", fields=["name"], limit=2)
    if not companies:
        return None
    return companies[0]["name"]


def main():
    global DEFAULT_COMPANY
    DEFAULT_COMPANY = detect_company()

    print("=" * 72)
    print(f" Phase 6 / Step 2a -- Employee backfill (DRY_RUN={DRY_RUN})")
    print(f" Site: {frappe.local.site}")
    print(f" Company: {DEFAULT_COMPANY}")
    print("=" * 72)

    report: list[str] = []
    report.append("# Step 2a -- Employee master backfill")
    report.append("")
    report.append(f"_Generated: {frappe.utils.now_datetime()}_  ")
    report.append(f"_Site: {frappe.local.site} | Company: {DEFAULT_COMPANY} | DRY_RUN={DRY_RUN}_")
    report.append("")

    seed_departments(report)
    seed_employment_types(report)
    seed_designations(report)
    seed_state_of_residence_field(report)

    create_babajide(report)
    for spec in RENAMES:
        report.append("## (Rename: Agent Itele 3rd -> Ismail Abdul Rahman)")
        report.append("")
        rename_employee(spec, report)
        report.append("")
    patch_off_payroll(report)
    patch_okhuoromi(report)
    archive_dedupes(report)
    archive_phantoms(report)
    patch_payroll_staff(report)

    if not DRY_RUN:
        frappe.db.commit()

    out = Path("/tmp/step2a_diff.md")
    out.write_text("\n".join(report), encoding="utf-8")
    print(f"\n[OK] wrote {out} ({sum(len(line) for line in report):,} chars)")
    print("\n----- last 40 lines preview -----\n")
    for line in report[-40:]:
        print(line)


try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
