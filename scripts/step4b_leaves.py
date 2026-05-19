"""
Phase 6 / Step 4b: Leave Types + Leave Period 2026 + Leave Policies + Leave
Policy Assignments per Sungas Junior + Senior staff handbooks.

Entitlements (Annual) by Grade Level:
  G1                  = 20 working days
  G2                  = 15 working days
  G3 - G7             = 10 working days

Sick / Maternity / Paternity / Compassionate / Casual are uniform per handbook.

Eligibility: handbook requires 6 months continuous service before annual leave
can be USED. ERP enforces via `applicable_after = 180` on the Annual leave type.

Carryover: handbook says forfeit anything not taken by Q1 of following year.
ERP: `is_carry_forward=1`, `expire_carry_forwarded_leaves_after_days=90`.

Toggle DRY_RUN=True to preview.

Run:
    curl -fsSL "<raw url>/scripts/step4b_leaves.py" -o /tmp/s4b.py
    bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/s4b.py').read())"
"""

from __future__ import annotations
from pathlib import Path
import frappe


DRY_RUN = False

LEAVE_PERIOD = {
    "name": "Sungas Leave Period 2026",
    "from_date": "2026-01-01",
    "to_date": "2026-12-31",
}


# Leave Types - per handbook (Junior Section 1 + parallel Senior provisions)
LEAVE_TYPES = [
    {
        "leave_type_name": "Annual Leave",
        "max_leaves_allowed": 20,             # G1 ceiling; per-grade allocation set in Leave Policy
        "is_carry_forward": 1,
        "max_carry_forwarded_leaves": 5,
        "expire_carry_forwarded_leaves_after_days": 90,
        "is_lwp": 0,
        "is_ppl": 0,
        "applicable_after": 180,               # 6-month waiting period (handbook)
        "include_holiday": 0,
        "allow_negative": 0,
        "is_optional_leave": 0,
        "is_compensatory": 0,
    },
    {
        "leave_type_name": "Sick Leave",
        "max_leaves_allowed": 12,              # 5 paid + up to 12 at discretion
        "is_carry_forward": 0,
        "include_holiday": 0,
        "applicable_after": 0,
        "is_lwp": 0,
    },
    {
        "leave_type_name": "Maternity Leave",
        "max_leaves_allowed": 90,              # 3 months continuous
        "is_carry_forward": 0,
        "include_holiday": 1,                  # 3 months calendar includes weekends
        "applicable_after": 0,
        "is_lwp": 0,
    },
    {
        "leave_type_name": "Paternity Leave",
        "max_leaves_allowed": 3,
        "max_continuous_days_allowed": "3",
        "is_carry_forward": 0,
        "include_holiday": 0,
        "applicable_after": 0,
        "is_lwp": 0,
    },
    {
        "leave_type_name": "Compassionate Leave",
        "max_leaves_allowed": 5,
        "is_carry_forward": 0,
        "include_holiday": 0,
        "applicable_after": 0,
        "is_lwp": 0,
    },
    {
        "leave_type_name": "Casual Leave",
        "max_leaves_allowed": 7,                # 1 week / year
        "max_continuous_days_allowed": "2",     # max 2 consecutive (handbook)
        "is_carry_forward": 0,
        "include_holiday": 0,
        "applicable_after": 0,
        "is_lwp": 0,
    },
]


# Per-grade Annual Leave allocation. Other leave types are uniform.
GRADE_ANNUAL_ALLOCATION = {
    "G1": 20,
    "G2": 15,
    "G3": 10, "G4": 10, "G5": 10, "G6": 10, "G7": 10,
}

UNIFORM_ALLOCATIONS = {
    "Sick Leave":          12,
    "Maternity Leave":     90,
    "Paternity Leave":      3,
    "Compassionate Leave":  5,
    "Casual Leave":         7,
}


def create_leave_types(report: list[str]) -> None:
    report.append("## 1. Leave Types (6)")
    report.append("")
    for spec in LEAVE_TYPES:
        name = spec["leave_type_name"]
        if frappe.db.exists("Leave Type", name):
            report.append(f"  = `{name}` already exists -- skip (manage via UI if updates needed)")
            continue
        if DRY_RUN:
            report.append(f"  + would-create `{name}` (max={spec.get('max_leaves_allowed')}, applicable_after={spec.get('applicable_after',0)}d)")
            continue
        try:
            frappe.get_doc({"doctype": "Leave Type", **spec}).insert(ignore_permissions=True)
            report.append(f"  + created `{name}`")
        except Exception as e:
            report.append(f"  ! ERROR creating `{name}`: {e}")
    report.append("")


def create_leave_period(report: list[str]) -> str | None:
    report.append("## 2. Leave Period 2026")
    report.append("")
    name = LEAVE_PERIOD["name"]
    if frappe.db.exists("Leave Period", name):
        report.append(f"  = `{name}` already exists")
        report.append("")
        return name
    if DRY_RUN:
        report.append(f"  + would-create `{name}` 2026-01-01 to 2026-12-31")
        report.append("")
        return name
    company = frappe.defaults.get_user_default("Company") or frappe.get_all("Company", limit=1)[0]["name"]
    doc = frappe.get_doc({
        "doctype": "Leave Period",
        "from_date": LEAVE_PERIOD["from_date"],
        "to_date": LEAVE_PERIOD["to_date"],
        "company": company,
        "is_active": 1,
    })
    doc.insert(ignore_permissions=True)
    report.append(f"  + created `{doc.name}`")
    report.append("")
    return doc.name


def create_leave_policies(report: list[str]) -> dict[str, str]:
    report.append("## 3. Leave Policies (G1, G2, G3-G7)")
    report.append("")
    # We need 3 policies, one for each Annual allocation tier
    policies = {
        "Sungas Leave Policy - G1 (20d Annual)":      20,
        "Sungas Leave Policy - G2 (15d Annual)":      15,
        "Sungas Leave Policy - G3-G7 (10d Annual)":   10,
    }
    created: dict[str, str] = {}
    for policy_name, annual_days in policies.items():
        if frappe.db.exists("Leave Policy", policy_name):
            created[policy_name] = policy_name
            report.append(f"  = `{policy_name}` already exists")
            continue
        if DRY_RUN:
            created[policy_name] = policy_name
            report.append(f"  + would-create `{policy_name}` (Annual={annual_days})")
            continue
        details = [{"leave_type": "Annual Leave", "annual_allocation": annual_days}]
        for lt, alloc in UNIFORM_ALLOCATIONS.items():
            details.append({"leave_type": lt, "annual_allocation": alloc})
        doc = frappe.get_doc({
            "doctype": "Leave Policy",
            "title": policy_name,
            "leave_policy_details": details,
        }).insert(ignore_permissions=True)
        created[policy_name] = doc.name
        report.append(f"  + created `{doc.name}`")
    report.append("")
    return created


GRADE_TO_POLICY = {
    "G1": "Sungas Leave Policy - G1 (20d Annual)",
    "G2": "Sungas Leave Policy - G2 (15d Annual)",
    "G3": "Sungas Leave Policy - G3-G7 (10d Annual)",
    "G4": "Sungas Leave Policy - G3-G7 (10d Annual)",
    "G5": "Sungas Leave Policy - G3-G7 (10d Annual)",
    "G6": "Sungas Leave Policy - G3-G7 (10d Annual)",
    "G7": "Sungas Leave Policy - G3-G7 (10d Annual)",
}


def assign_leave_policies(period: str | None, policies: dict[str, str], report: list[str]) -> None:
    report.append("## 4. Leave Policy Assignments (per active employee)")
    report.append("")
    if not period:
        report.append("  ! No leave period -- skip")
        return
    employees = frappe.get_all(
        "Employee",
        filters={"status": "Active"},
        fields=["name", "employee_name", "grade_level", "date_of_joining", "company"],
    )
    company = (employees[0].get("company") if employees else None) or frappe.defaults.get_user_default("Company")

    by_policy: dict[str, int] = {}
    skipped = 0
    created = 0
    errors = []

    for emp in employees:
        grade = emp.get("grade_level") or "G6"
        policy_name = GRADE_TO_POLICY.get(grade)
        if not policy_name:
            skipped += 1
            continue
        # Skip if existing active assignment exists for this period
        existing = frappe.db.exists(
            "Leave Policy Assignment",
            {
                "employee": emp["name"],
                "leave_period": period,
                "docstatus": ["<", 2],
            },
        )
        if existing:
            by_policy.setdefault(policy_name, 0)
            by_policy[policy_name] += 1
            continue
        by_policy.setdefault(policy_name, 0)
        by_policy[policy_name] += 1
        if DRY_RUN:
            created += 1
            continue
        try:
            doc = frappe.get_doc({
                "doctype": "Leave Policy Assignment",
                "employee": emp["name"],
                "assignment_based_on": "Leave Period",
                "leave_policy": policy_name,
                "leave_period": period,
                "effective_from": LEAVE_PERIOD["from_date"],
                "effective_to": LEAVE_PERIOD["to_date"],
                "company": company,
            }).insert(ignore_permissions=True)
            doc.submit()
            created += 1
        except Exception as e:
            errors.append((emp["name"], str(e)))

    report.append(f"  Active employees: {len(employees)}")
    report.append(f"  Assignments {'projected' if DRY_RUN else 'created+submitted'}: {created}")
    report.append(f"  Skipped (no grade): {skipped}")
    report.append(f"  Errors: {len(errors)}")
    report.append("")
    report.append("  Distribution by policy:")
    for policy_name, n in sorted(by_policy.items(), key=lambda x: -x[1]):
        report.append(f"    {n:3d}x  {policy_name}")
    if errors:
        report.append("")
        report.append("  Error details:")
        for emp_id, err in errors[:20]:
            report.append(f"    - {emp_id}: {err}")
    report.append("")


def main():
    print("=" * 72)
    print(f" Phase 6 / Step 4b -- Leave Types + Policies + Assignments (DRY_RUN={DRY_RUN})")
    print("=" * 72)

    report: list[str] = []
    report.append("# Step 4b -- Leave Types + Leave Period + Leave Policy Assignments")
    report.append("")
    report.append(f"_Generated: {frappe.utils.now_datetime()} | Site: {frappe.local.site} | DRY_RUN={DRY_RUN}_")
    report.append("")

    create_leave_types(report)
    period = create_leave_period(report)
    policies = create_leave_policies(report)
    assign_leave_policies(period, policies, report)

    if not DRY_RUN:
        frappe.db.commit()

    p = Path("/tmp/step4b_leaves.md")
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
