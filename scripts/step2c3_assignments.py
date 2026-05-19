"""
Phase 6 / Step 2c.3: Cost Centers + payroll_cost_center field + 217 Salary Structure Assignments.

Idempotent. Toggle DRY_RUN=True to preview.

Sections:
  1. Create 19 new Cost Centers (XX001 Operations + Oshodi/Ebute/HQ extras)
  2. Add Employee.payroll_cost_center custom field
  3. Populate payroll_cost_center for all 217 employees via routing rules
  4. Create 217 Salary Structure Assignments (base = April 2026 gross,
     from_date = 2026-06-01, links to 'Sungas Standard' structure)

Output: /tmp/step2c3_assignments.md

Run:
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/feat/sungas-customizations/scripts/step2c3_assignments.py" -o /tmp/step2c3_assignments.py
    bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/step2c3_assignments.py').read())"
"""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

import frappe


DRY_RUN = False
COMPANY: str | None = None
ABBR: str | None = None

STRUCTURE_NAME = "Sungas Standard"
ASSIGNMENT_FROM_DATE = "2026-06-01"


# ---------------------------------------------------------------------------
# 1. Cost Center spec -- new CCs to create
# ---------------------------------------------------------------------------

# (cc_number, label, outlet, parent_cc_label_or_number)
# Parent is found by looking up the matching XX002 CC's parent (so siblings live together)
NEW_CCS = [
    # New Operations CCs mirroring existing XX002 Sales CCs
    ("11001", "Operations Ikeja",          "Ikeja"),
    ("12001", "Operations Pedro",          "Pedro"),
    ("21001", "Operations Eleme",          "Eleme"),
    ("22001", "Operations Reclamation",    "Reclamation"),
    ("31001", "Operations Upper Mission",  "Upper Mission"),
    ("32001", "Operations Ekehuan",        "Ekehuan"),
    ("33001", "Operations Okhuoromi",      "Okhuoromi"),
    ("34001", "Operations Idowina",        "Idowina"),
    ("36001", "Operations Idokpa",         "Idokpa"),
    ("41001", "Operations Aseese",         "Aseese"),
    ("42001", "Operations Maba",           "Maba"),
    ("43001", "Operations Sefu",           "Sefu"),
    ("51001", "Operations Iju-Otta",       "Iju-Otta"),
    ("53001", "Operations Ijoko",          "Ijoko"),
    ("54001", "Operations Osi-Otta",       "Osi-Otta"),
    ("61001", "Operations Asaba",          "Asaba"),
    # Missing outlets
    ("13001", "Operations Oshodi",         "Oshodi"),
    ("13002", "Sales and Marketing Oshodi","Oshodi"),
    ("14001", "Operations Ebute",          "Ebute"),
    ("14002", "Sales and Marketing Ebute", "Ebute"),
    ("70013", "Operations Headquarters",   "Headquarters"),
]

def _projected_cc_name(outlet: str, kind: str) -> str | None:
    """If a new CC is queued in NEW_CCS for this outlet+kind, return its projected ERP name."""
    label_prefix = "Operations " if kind == "op" else "Sales and Marketing "
    for number, label, ol in NEW_CCS:
        if ol == outlet and label.startswith(label_prefix):
            return f"{number} - {label} - {ABBR}"
    return None


def find_sales_cc_with_parent(outlet: str) -> dict | None:
    """Return existing XX002 Sales CC for an outlet, with name + parent_cost_center."""
    rows = frappe.get_all(
        "Cost Center",
        filters={"is_group": 0, "cost_center_name": ["like", f"%Sales and Marketing {outlet}%"]},
        fields=["name", "parent_cost_center"],
        limit=1,
    )
    return rows[0] if rows else None


def find_sales_cc(outlet: str) -> str | None:
    """Return Sales CC name (existing or projected from NEW_CCS for new outlets)."""
    row = find_sales_cc_with_parent(outlet)
    if row:
        return row["name"]
    proj = _projected_cc_name(outlet, "sales")
    if proj and frappe.db.exists("Cost Center", proj):
        return proj
    return proj  # may be None or projected (DRY_RUN before insert)


def find_op_cc(outlet: str) -> str | None:
    """Return Operations CC name (existing or projected from NEW_CCS)."""
    proj = _projected_cc_name(outlet, "op")
    if proj and frappe.db.exists("Cost Center", proj):
        return proj
    if proj:
        return proj  # DRY_RUN: CC will be created on live run
    rows = frappe.get_all(
        "Cost Center",
        filters={"is_group": 0, "cost_center_name": ["like", f"%Operations {outlet}%"]},
        fields=["name"],
        limit=1,
    )
    return rows[0]["name"] if rows else None


def find_hq_cc(account_number: str) -> str | None:
    """Find HQ cost center by its account number prefix (existing or projected)."""
    rows = frappe.get_all(
        "Cost Center",
        filters={"is_group": 0, "name": ["like", f"{account_number} -%"]},
        fields=["name"],
        limit=1,
    )
    if rows:
        return rows[0]["name"]
    # Projection (e.g. 70013 Operations HQ in DRY_RUN before insert)
    for number, label, _ol in NEW_CCS:
        if number == account_number:
            return f"{number} - {label} - {ABBR}"
    return None


def create_cost_centers(report: list[str]) -> None:
    report.append("## 1. Create new Cost Centers")
    report.append("")

    # Find a default parent (most outlets have CCs under company root)
    default_parent = frappe.db.get_value("Cost Center", {"is_group": 1, "company": COMPANY, "cost_center_name": COMPANY}, "name")
    if not default_parent:
        rows = frappe.get_all("Cost Center", filters={"is_group": 1, "company": COMPANY}, fields=["name"], limit=1)
        default_parent = rows[0]["name"] if rows else None

    for number, label, outlet in NEW_CCS:
        target_name = f"{number} - {label} - {ABBR}"
        if frappe.db.exists("Cost Center", target_name):
            report.append(f"  = `{target_name}` already exists")
            continue
        # Find sibling parent if possible
        sibling = find_sales_cc_with_parent(outlet) if outlet not in ("Headquarters",) else None
        parent = sibling["parent_cost_center"] if sibling else default_parent
        if DRY_RUN:
            report.append(f"  + would-insert `{target_name}` under `{parent}`")
            continue
        doc = frappe.get_doc({
            "doctype": "Cost Center",
            "cost_center_name": f"{number} - {label}",
            "parent_cost_center": parent,
            "is_group": 0,
            "company": COMPANY,
        }).insert(ignore_permissions=True, ignore_if_duplicate=True)
        report.append(f"  + inserted `{doc.name}` under `{parent}`")
    report.append("")


# ---------------------------------------------------------------------------
# 2. Add Employee.payroll_cost_center custom field
# ---------------------------------------------------------------------------

def add_payroll_cc_field(report: list[str]) -> None:
    report.append("## 2. Custom field Employee.payroll_cost_center")
    report.append("")
    cf_name = "Employee-payroll_cost_center"
    if frappe.db.exists("Custom Field", cf_name):
        report.append("  = already exists")
        report.append("")
        return
    if DRY_RUN:
        report.append("  + would-insert")
        report.append("")
        return
    frappe.get_doc({
        "doctype": "Custom Field",
        "dt": "Employee",
        "fieldname": "payroll_cost_center",
        "label": "Payroll Cost Center",
        "fieldtype": "Link",
        "options": "Cost Center",
        "insert_after": "branch",
        "description": "Cost Center to which this employee's monthly salary expense is posted.",
    }).insert(ignore_permissions=True, ignore_if_duplicate=True)
    report.append("  + inserted")
    report.append("")


# ---------------------------------------------------------------------------
# 3. Routing rules
# ---------------------------------------------------------------------------

HQ_FINANCE_DESIGNATIONS = {
    "Accountant", "Finance Manager", "Account Officer", "Account Receivable Officer",
}

# HQ CC numbers (resolved at runtime)
HQ_CC_PREFIX = {
    "Finance":           "70001",
    "Sales_HO":          "70002",
    "Procurement":       "70003",
    "HR_Admin":          "70006",
    "Internal_Control":  "70010",
    "Executive":         "70011",
    "Operations_HQ":     "70013",  # new
}


def resolve_cc_for_employee(emp: dict, hq_resolved: dict, report_warn: list[str]) -> str | None:
    """Resolve Cost Center based on (designation, department, branch)."""
    desig = emp.get("designation") or ""
    dept = emp.get("department") or ""
    branch = emp.get("branch") or ""

    # Special: HQ finance staff override
    if desig in HQ_FINANCE_DESIGNATIONS:
        return hq_resolved.get("Finance")

    # Special: Cashiers always route to outlet Sales CC
    if desig == "Cashier":
        return find_sales_cc(branch)

    # Department-level routing
    if "Sales" in dept:  # Sales & Marketing
        return find_sales_cc(branch) or hq_resolved.get("Sales_HO")

    if "Operations" in dept or "Logistics" in dept or "Technical" in dept:
        return find_op_cc(branch) or hq_resolved.get("Operations_HQ")

    if "Customer Service" in dept:
        return hq_resolved.get("Sales_HO")

    if "HR" in dept:
        return hq_resolved.get("HR_Admin")

    if "Internal Control" in dept:
        return hq_resolved.get("Internal_Control")

    if "Executive" in dept:
        return hq_resolved.get("Executive")

    if "Stores" in dept:
        return hq_resolved.get("Procurement")

    if "Finance" in dept:
        # Could be a Cashier (handled above) -- non-cashier non-HQ Finance fallback
        return hq_resolved.get("Finance")

    report_warn.append(f"    ⚠ unresolved: {emp['name']} ({emp['employee_name']}) -- desig={desig!r}, dept={dept!r}, branch={branch!r}")
    return None


# ---------------------------------------------------------------------------
# 4. Populate Employee.payroll_cost_center
# ---------------------------------------------------------------------------

def populate_payroll_cc(report: list[str]) -> dict[str, str]:
    report.append("## 3. Populate Employee.payroll_cost_center")
    report.append("")

    # Resolve HQ CCs
    hq_resolved = {}
    for key, prefix in HQ_CC_PREFIX.items():
        cc = find_hq_cc(prefix)
        if cc:
            hq_resolved[key] = cc
        else:
            report.append(f"  ⚠ HQ CC for `{key}` (prefix {prefix}) NOT FOUND -- skip")
    report.append("")

    employees = frappe.get_all(
        "Employee",
        filters={"status": "Active"},
        fields=["name", "employee_name", "designation", "department", "branch", "employment_type"],
    )

    routed = 0
    skipped = 0
    by_cc = defaultdict(int)
    warnings: list[str] = []
    emp_to_cc: dict[str, str] = {}

    for emp in employees:
        cc = resolve_cc_for_employee(emp, hq_resolved, warnings)
        if not cc:
            skipped += 1
            continue
        emp_to_cc[emp["name"]] = cc
        by_cc[cc] += 1
        if DRY_RUN:
            routed += 1
            continue
        frappe.db.set_value("Employee", emp["name"], "payroll_cost_center", cc)
        routed += 1

    report.append(f"  - Routed: **{routed}** / {len(employees)}")
    report.append(f"  - Skipped (no rule matched): {skipped}")
    report.append("")
    report.append("  Distribution across cost centers:")
    for cc, n in sorted(by_cc.items(), key=lambda x: -x[1])[:20]:
        report.append(f"    {n:3d}x  {cc}")
    if warnings:
        report.append("")
        report.append("  Warnings:")
        for w in warnings[:20]:
            report.append(w)
        if len(warnings) > 20:
            report.append(f"    ... and {len(warnings)-20} more")
    report.append("")
    return emp_to_cc


# ---------------------------------------------------------------------------
# 5. Create 217 Salary Structure Assignments
# ---------------------------------------------------------------------------

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


def create_assignments(emp_to_cc: dict[str, str], report: list[str]) -> None:
    report.append("## 4. Salary Structure Assignments (base = April 2026 gross)")
    report.append("")

    if not frappe.db.exists("Salary Structure", STRUCTURE_NAME):
        report.append(f"  ! Salary Structure `{STRUCTURE_NAME}` not found -- abort")
        return

    sys.path.insert(0, "/tmp")
    try:
        from _payroll_roster import PAYROLL_APR_2026 as ROSTER  # type: ignore
    except Exception as exc:
        report.append(f"  ! could not import /tmp/_payroll_roster.py: {exc}")
        return

    # Build employee index
    idx = defaultdict(list)
    for emp in frappe.get_all(
        "Employee",
        filters={"status": "Active"},
        fields=["name", "employee_name", "designation", "department", "branch"],
    ):
        idx[_tokenise(emp["employee_name"] or "")].append(emp)

    created = updated = unresolved = errors = 0
    error_msgs = []

    for row in ROSTER:
        emp = lookup_employee(row["name"], idx)
        if not emp:
            unresolved += 1
            continue

        emp_id = emp["name"]
        cc = emp_to_cc.get(emp_id)
        base = float(row["gross"])

        # Check existing assignment
        existing = frappe.get_all(
            "Salary Structure Assignment",
            filters={
                "employee": emp_id,
                "salary_structure": STRUCTURE_NAME,
                "from_date": ASSIGNMENT_FROM_DATE,
                "docstatus": ["<", 2],
            },
            fields=["name", "docstatus", "base"],
            limit=1,
        )

        if existing:
            existing_doc = existing[0]
            if existing_doc["docstatus"] == 1:
                # Submitted -- can't modify; cancel + re-create would be too risky
                updated += 1
                continue
            if DRY_RUN:
                updated += 1
                continue
            try:
                doc = frappe.get_doc("Salary Structure Assignment", existing_doc["name"])
                doc.base = base
                if cc and frappe.get_meta("Salary Structure Assignment").has_field("payroll_cost_center"):
                    doc.payroll_cost_center = cc
                doc.save(ignore_permissions=True)
                updated += 1
            except Exception as e:
                errors += 1
                error_msgs.append(f"    {emp_id}: {e}")
            continue

        if DRY_RUN:
            created += 1
            continue

        try:
            data = {
                "doctype": "Salary Structure Assignment",
                "employee": emp_id,
                "salary_structure": STRUCTURE_NAME,
                "from_date": ASSIGNMENT_FROM_DATE,
                "base": base,
                "company": COMPANY,
            }
            if cc and frappe.get_meta("Salary Structure Assignment").has_field("payroll_cost_center"):
                data["payroll_cost_center"] = cc
            doc = frappe.get_doc(data).insert(ignore_permissions=True)
            doc.submit()
            created += 1
        except Exception as e:
            errors += 1
            error_msgs.append(f"    {emp_id} ({row['name']}, base={base}): {e}")

    report.append(f"  - Created (new + submitted): **{created}**")
    report.append(f"  - Updated existing draft: {updated}")
    report.append(f"  - Unresolved (no ERP match): {unresolved}")
    report.append(f"  - Errors: {errors}")
    if error_msgs:
        report.append("")
        report.append("  Error details:")
        for m in error_msgs[:20]:
            report.append(m)
        if len(error_msgs) > 20:
            report.append(f"    ... and {len(error_msgs)-20} more")
    report.append("")


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def detect_company() -> tuple[str | None, str | None]:
    rows = frappe.get_all("Company", fields=["name", "abbr"], limit=2)
    return (rows[0]["name"], rows[0]["abbr"]) if rows else (None, None)


def main():
    global COMPANY, ABBR
    COMPANY, ABBR = detect_company()

    print("=" * 72)
    print(f" Phase 6 / Step 2c.3 -- CC + payroll_cc field + 217 SSAs (DRY_RUN={DRY_RUN})")
    print(f" Company: {COMPANY} (abbr={ABBR})")
    print("=" * 72)

    report: list[str] = []
    report.append("# Step 2c.3 -- Cost Centers + Salary Structure Assignments")
    report.append("")
    report.append(f"_Generated: {frappe.utils.now_datetime()}_  ")
    report.append(f"_Site: {frappe.local.site} | Company: {COMPANY} | DRY_RUN={DRY_RUN}_")
    report.append("")

    create_cost_centers(report)
    add_payroll_cc_field(report)
    emp_to_cc = populate_payroll_cc(report)
    create_assignments(emp_to_cc, report)

    if not DRY_RUN:
        frappe.db.commit()

    p = Path("/tmp/step2c3_assignments.md")
    p.write_text("\n".join(report), encoding="utf-8")
    print(f"\n[OK] wrote {p}")
    print()
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
