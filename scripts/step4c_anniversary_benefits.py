"""
Phase 6 / Step 4c: Anniversary benefits salary components.

Adds two Earnings components to 'Sungas Standard' salary structure:

  1. Leave Allowance (LV-ALW)
     - Per Junior+Senior Handbook: "10% of annual basic salary, paid in the
       month of the employee's anniversary start date"
     - Eligible: continuous service >= 12 months at slip start_date
     - Amount: 0.10 * BS * 12 = 1.2 * monthly basic (one-shot annual lump)
     - Posted as taxable income; PAYE formula already handles it (gross_pay
       includes earnings sum)

  2. 13th Month (TH-MO)
     - Per Handbook: "sum equal to the monthly basic salary as 13th month
       benefit in the month of December"
     - Eligible: continuous service >= 12 months at slip start_date AND
                 hire date before Aug 1 of current year
     - Toggle: Employee.eligible_for_13th_month (Check, default 1)
       -> Management can flip globally via /scripts/toggle_13th_month.py
     - Amount: 1.0 * BS (one-shot December lump)

Both fire only once per year in the right month. Safe to leave in the
structure permanently.

Toggle DRY_RUN=True to preview.

Run:
    curl -fsSL "<raw url>/scripts/step4c_anniversary_benefits.py" -o /tmp/s4c.py
    bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/s4c.py').read())"
"""

from __future__ import annotations
from pathlib import Path
import frappe


DRY_RUN = False
STRUCTURE_NAME = "Sungas Standard"


# Leave Allowance: 10% of annual basic, paid in anniversary month, after 12 months service.
# Only fires for staff with a grade_level set (G1-G7) -- service providers excluded.
LV_ALW_FORMULA = (
    "(0.10 * BS * 12) "
    "if (employee.grade_level "
    "and employee.date_of_joining "
    "and getdate(start_date).month == getdate(employee.date_of_joining).month "
    "and date_diff(start_date, employee.date_of_joining) >= 365) "
    "else 0"
)

# 13th Month: 1x basic in December, after 12 months service, hired before Aug 1.
# Gated by grade_level (excludes service providers) AND eligible_for_13th_month toggle.
TH_MO_FORMULA = (
    "BS "
    "if (employee.eligible_for_13th_month "
    "and employee.grade_level "
    "and getdate(start_date).month == 12 "
    "and employee.date_of_joining "
    "and date_diff(start_date, employee.date_of_joining) >= 365 "
    "and getdate(employee.date_of_joining).month < 8) "
    "else 0"
)


def ensure_salary_component(name: str, abbr: str, formula: str, report: list[str]) -> None:
    report.append(f"### Component: `{name}` ({abbr})")
    if frappe.db.exists("Salary Component", name):
        sc = frappe.get_doc("Salary Component", name)
        needs_update = (
            sc.formula != formula
            or sc.amount_based_on_formula != 1
            or sc.type != "Earning"
        )
        if not needs_update:
            report.append("  = already up-to-date")
            report.append("")
            return
        if DRY_RUN:
            report.append("  + would-update formula / type")
            report.append("")
            return
        sc.type = "Earning"
        sc.amount_based_on_formula = 1
        sc.formula = formula
        sc.save(ignore_permissions=True)
        report.append("  + updated formula")
        report.append("")
        return

    if DRY_RUN:
        report.append("  + would-create (Earning, formula-based)")
        report.append("")
        return

    frappe.get_doc({
        "doctype": "Salary Component",
        "salary_component": name,
        "salary_component_abbr": abbr,
        "type": "Earning",
        "depends_on_payment_days": 0,
        "amount_based_on_formula": 1,
        "formula": formula,
        "is_tax_applicable": 1,
        "statistical_component": 0,
    }).insert(ignore_permissions=True)
    report.append("  + created")
    report.append("")


def add_components_to_structure(report: list[str]) -> None:
    report.append("## 2. Attach components to `Sungas Standard` structure")
    report.append("")
    if not frappe.db.exists("Salary Structure", STRUCTURE_NAME):
        report.append(f"  ! Salary Structure `{STRUCTURE_NAME}` not found -- abort")
        return

    ss = frappe.get_doc("Salary Structure", STRUCTURE_NAME)
    existing_earnings = {row.salary_component for row in ss.earnings}

    additions = []
    for cname, abbr, formula in (
        ("Leave Allowance", "LV-ALW", LV_ALW_FORMULA),
        ("13th Month",      "TH-MO",  TH_MO_FORMULA),
    ):
        if cname in existing_earnings:
            report.append(f"  = `{cname}` already attached")
            continue
        if DRY_RUN:
            report.append(f"  + would-attach `{cname}`")
            additions.append(cname)
            continue
        ss.append("earnings", {
            "salary_component": cname,
            "abbr": abbr,
            "amount_based_on_formula": 1,
            "formula": formula,
            "depends_on_payment_days": 0,
        })
        additions.append(cname)

    if additions and not DRY_RUN:
        ss.save(ignore_permissions=True)
        report.append(f"  + saved structure (attached {len(additions)} components)")
    report.append("")


def main():
    print("=" * 72)
    print(f" Phase 6 / Step 4c -- Anniversary Benefits Salary Components (DRY_RUN={DRY_RUN})")
    print("=" * 72)

    report: list[str] = []
    report.append("# Step 4c -- Leave Allowance + 13th Month")
    report.append("")
    report.append(f"_Generated: {frappe.utils.now_datetime()} | Site: {frappe.local.site} | DRY_RUN={DRY_RUN}_")
    report.append("")
    report.append("## 1. Salary Components")
    report.append("")

    ensure_salary_component("Leave Allowance", "LV-ALW", LV_ALW_FORMULA, report)
    ensure_salary_component("13th Month",      "TH-MO",  TH_MO_FORMULA,  report)

    add_components_to_structure(report)

    if not DRY_RUN:
        frappe.db.commit()

    p = Path("/tmp/step4c_benefits.md")
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
