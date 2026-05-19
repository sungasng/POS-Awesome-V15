"""
Phase 6 / Step 2c (Part 1): HMO model + Salary Structure.

What this does (idempotent, DRY_RUN-safe):
  1. Adds 4 custom fields to Employee:
       - hmo_plan_name              Data
       - hmo_coverage_type          Select (Individual / Family)
       - hmo_monthly_premium_company_paid  Currency (default 8666)
       - hmo_monthly_topup_staff_paid      Currency (default 0)
  2. Updates `Medical Allowance` Salary Component:
       - Sets formula -> looks up Employee.hmo_monthly_premium_company_paid
       - Flips to STATISTICAL (informational, excluded from Net Pay & PAYE)
  3. Creates new `HMO Top-up (Staff Paid)` Salary Component:
       - Deduction, real (reduces Net Pay)
       - Formula -> looks up Employee.hmo_monthly_topup_staff_paid
  4. Backfills 217 payroll employees with:
       - hmo_monthly_premium_company_paid = 8666 (matches April baseline)
       - hmo_coverage_type = "Family" for designations in SENIOR_FAMILY_TIER
                             "Individual" otherwise
  5. Creates ONE Salary Structure `Sungas Standard` linking 13 components.

Idempotent. Toggle DRY_RUN=True to preview.

Output: /tmp/step2c_hmo_structure.md

Run:
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/feat/sungas-customizations/scripts/step2c_hmo_structure.py" -o /tmp/step2c_hmo_structure.py
    bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/step2c_hmo_structure.py').read())"
"""

from __future__ import annotations

from pathlib import Path

import frappe


DRY_RUN = False
COMPANY: str | None = None

# Designations entitled to FAMILY HMO coverage by default
SENIOR_FAMILY_TIER = {
    "Plant Manager",
    "Operations Manager",
    "Head of Sales & Marketing",
    "Head of Human Resources & Admin",
    "Head of Internal Control",
    "Head of Technical Unit",
    "Finance Manager",
    "Chief Operating Officer",
}


# ---------------------------------------------------------------------------
# 1. Custom Fields on Employee
# ---------------------------------------------------------------------------

CUSTOM_FIELDS_HMO = [
    {
        "fieldname": "hmo_section_break",
        "label": "HMO / Health Insurance",
        "fieldtype": "Section Break",
        "insert_after": "state_of_residence",
        "collapsible": 1,
    },
    {
        "fieldname": "hmo_plan_name",
        "label": "HMO Plan Name",
        "fieldtype": "Data",
        "insert_after": "hmo_section_break",
        "description": "Free-text. e.g. 'Hygeia Gold Family', 'AXA Mansard Silver'.",
    },
    {
        "fieldname": "hmo_coverage_type",
        "label": "HMO Coverage Type",
        "fieldtype": "Select",
        "options": "\nIndividual\nFamily",
        "default": "Individual",
        "insert_after": "hmo_plan_name",
    },
    {
        "fieldname": "hmo_column_break",
        "fieldtype": "Column Break",
        "insert_after": "hmo_coverage_type",
    },
    {
        "fieldname": "hmo_monthly_premium_company_paid",
        "label": "HMO Monthly Premium (Company Paid)",
        "fieldtype": "Currency",
        "default": 8666,
        "insert_after": "hmo_column_break",
        "description": "Benchmark premium the COMPANY pays directly to the HMO. Shown on payslip as Medical Allowance (statistical -- does NOT affect Net Pay).",
    },
    {
        "fieldname": "hmo_monthly_topup_staff_paid",
        "label": "HMO Monthly Top-up (Staff Paid)",
        "fieldtype": "Currency",
        "default": 0,
        "insert_after": "hmo_monthly_premium_company_paid",
        "description": "Optional. Difference between staff's chosen plan and company benchmark. Deducted from Net Pay.",
    },
]


def seed_hmo_custom_fields(report: list[str]) -> None:
    report.append("## 1. Custom Fields on Employee (HMO section)")
    report.append("")
    for spec in CUSTOM_FIELDS_HMO:
        cf_name = f"Employee-{spec['fieldname']}"
        if frappe.db.exists("Custom Field", cf_name):
            report.append(f"  = `{cf_name}` already exists")
            continue
        if DRY_RUN:
            report.append(f"  + would-insert `{cf_name}` ({spec.get('fieldtype')})")
            continue
        frappe.get_doc({
            "doctype": "Custom Field",
            "dt": "Employee",
            **spec,
        }).insert(ignore_permissions=True, ignore_if_duplicate=True)
        report.append(f"  + inserted `{cf_name}` ({spec.get('fieldtype')})")
    report.append("")


# ---------------------------------------------------------------------------
# 2. Update Medical Allowance to statistical + formula-from-Employee-field
# ---------------------------------------------------------------------------

def fix_paye_flag(report: list[str]) -> None:
    report.append("## 2b. Fix PAYE: clear `variable_based_on_taxable_salary` flag + repair formula")
    report.append("")
    if not frappe.db.exists("Salary Component", "PAYE"):
        report.append("  ! PAYE component not found")
        report.append("")
        return
    doc = frappe.get_doc("Salary Component", "PAYE")

    # Single-expression NTAA 2025 stub. Cumulative tax at each band ceiling baked in.
    new_formula = (
        "((0 if max(0, gross_pay*12 - 500000) <= 800000 "
        "else (max(0, gross_pay*12 - 500000) - 800000) * 0.15 "
        "  if max(0, gross_pay*12 - 500000) <= 3000000 "
        "else 330000 + (max(0, gross_pay*12 - 500000) - 3000000) * 0.18 "
        "  if max(0, gross_pay*12 - 500000) <= 12000000 "
        "else 1950000 + (max(0, gross_pay*12 - 500000) - 12000000) * 0.21 "
        "  if max(0, gross_pay*12 - 500000) <= 25000000 "
        "else 4680000 + (max(0, gross_pay*12 - 500000) - 25000000) * 0.23 "
        "  if max(0, gross_pay*12 - 500000) <= 50000000 "
        "else 10430000 + (max(0, gross_pay*12 - 500000) - 50000000) * 0.25)"
        ") / 12"
    )

    changes = []
    if doc.get("variable_based_on_taxable_salary"):
        doc.variable_based_on_taxable_salary = 0
        changes.append("cleared variable_based_on_taxable_salary flag")
    if doc.formula != new_formula:
        doc.formula = new_formula
        doc.amount_based_on_formula = 1
        changes.append("repaired formula to single-expression ternary chain")

    if not changes:
        report.append("  = no changes needed")
        report.append("")
        return
    if DRY_RUN:
        report.append("  ~ would-apply: " + "; ".join(changes))
        report.append("")
        return
    doc.save(ignore_permissions=True)
    report.append("  ~ " + "; ".join(changes))
    report.append("")



def update_medical_allowance(report: list[str]) -> None:
    report.append("## 2. Update `Medical Allowance` -> statistical, premium-driven")
    report.append("")
    if not frappe.db.exists("Salary Component", "Medical Allowance"):
        report.append("  ! `Medical Allowance` not found (run Step 2b first)")
        return
    doc = frappe.get_doc("Salary Component", "Medical Allowance")
    patch = {
        "amount_based_on_formula": 1,
        "formula": (
            'frappe.db.get_value("Employee", employee, '
            '"hmo_monthly_premium_company_paid") or 0'
        ),
        "is_tax_applicable": 0,
        "do_not_include_in_total": 1,
        "statistical_component": 1,
        "depends_on_payment_days": 1,
    }
    changed = False
    for k, v in patch.items():
        if doc.get(k) != v:
            doc.set(k, v)
            changed = True
    if DRY_RUN:
        report.append(f"  ~ would-update Medical Allowance ({'changes' if changed else 'no-op'})")
        return
    if changed:
        doc.save(ignore_permissions=True)
        report.append("  ~ updated Medical Allowance -> statistical, formula now reads Employee.hmo_monthly_premium_company_paid")
    else:
        report.append("  = Medical Allowance already configured")
    report.append("")


# ---------------------------------------------------------------------------
# 3. Add HMO Top-up (Staff Paid) deduction component
# ---------------------------------------------------------------------------

def add_hmo_topup_component(report: list[str]) -> None:
    report.append("## 3. Add `HMO Top-up (Staff Paid)` Salary Component")
    report.append("")
    name = "HMO Top-up (Staff Paid)"
    if frappe.db.exists("Salary Component", name):
        report.append(f"  = `{name}` already exists")
        report.append("")
        return
    if DRY_RUN:
        report.append(f"  + would-insert `{name}`")
        report.append("")
        return
    frappe.get_doc({
        "doctype": "Salary Component",
        "salary_component": name,
        "salary_component_abbr": "HMO-TU",
        "type": "Deduction",
        "amount_based_on_formula": 1,
        "formula": (
            'frappe.db.get_value("Employee", employee, '
            '"hmo_monthly_topup_staff_paid") or 0'
        ),
        "is_tax_applicable": 0,
        "depends_on_payment_days": 1,
        "do_not_include_in_total": 0,
    }).insert(ignore_permissions=True, ignore_if_duplicate=True)
    report.append(f"  + inserted `{name}` (HMO-TU, Deduction)")
    report.append("")


# ---------------------------------------------------------------------------
# 4. Backfill HMO defaults across 217 active employees
# ---------------------------------------------------------------------------

def backfill_hmo_defaults(report: list[str]) -> None:
    report.append("## 4. Backfill HMO defaults on Active payroll employees")
    report.append("")

    # Need fields to exist before mutating values
    meta = frappe.get_meta("Employee")
    for required in ("hmo_coverage_type", "hmo_monthly_premium_company_paid"):
        if not meta.has_field(required):
            report.append(f"  ! field `{required}` missing -- did Step 4.1 succeed? Aborting backfill.")
            return

    employees = frappe.get_all(
        "Employee",
        filters={"status": "Active", "employment_type": ["in", ["Permanent", "Contract"]]},
        fields=["name", "employee_name", "designation"],
    )

    individual_count = family_count = 0
    skipped = 0
    for emp in employees:
        coverage = "Family" if emp.get("designation") in SENIOR_FAMILY_TIER else "Individual"
        if DRY_RUN:
            if coverage == "Family":
                family_count += 1
            else:
                individual_count += 1
            continue
        doc = frappe.get_doc("Employee", emp["name"])
        changed = False
        if not doc.get("hmo_monthly_premium_company_paid"):
            doc.hmo_monthly_premium_company_paid = 8666
            changed = True
        if not doc.get("hmo_coverage_type"):
            doc.hmo_coverage_type = coverage
            changed = True
        elif emp.get("designation") in SENIOR_FAMILY_TIER and doc.hmo_coverage_type != "Family":
            # promote to Family for senior tier even if previously set
            doc.hmo_coverage_type = "Family"
            changed = True
        if changed:
            doc.save(ignore_permissions=True)
            if doc.hmo_coverage_type == "Family":
                family_count += 1
            else:
                individual_count += 1
        else:
            skipped += 1

    report.append(f"  - Individual coverage: **{individual_count}**")
    report.append(f"  - Family coverage:     **{family_count}**")
    report.append(f"  - Already set:         {skipped}")
    report.append("")
    report.append("  _Senior tier (auto-Family):_ " + ", ".join(sorted(SENIOR_FAMILY_TIER)))
    report.append("")


# ---------------------------------------------------------------------------
# 5. Salary Structure -- `Sungas Standard`
# ---------------------------------------------------------------------------

STRUCTURE_NAME = "Sungas Standard"

STRUCTURE_EARNINGS = [
    "Basic Pay",
    "Transport Allowance",
    "Housing Allowance",
    "Cost of Living Allowance",
    "Medical Allowance",  # statistical, premium-driven
]

STRUCTURE_DEDUCTIONS = [
    "NSITF",                       # statistical, employer cost
    "Pension Employee",
    "Pension Employer",            # statistical, employer cost
    "PAYE",
    "HMO Top-up (Staff Paid)",
    "Loan Repayment",              # manual
    "COOP Loan Repayment",         # manual
    "Cooperative Contribution",    # manual
]


def upsert_salary_structure(report: list[str]) -> None:
    report.append(f"## 5. Salary Structure `{STRUCTURE_NAME}`")
    report.append("")

    if frappe.db.exists("Salary Structure", STRUCTURE_NAME):
        report.append(f"  = `{STRUCTURE_NAME}` already exists -- skipping re-create")
        report.append("     (delete + re-run if structure needs changes)")
        report.append("")
        return

    if DRY_RUN:
        report.append(f"  + would-insert `{STRUCTURE_NAME}` (5 earnings, 8 deductions)")
        report.append("")
        return

    earnings_rows = []
    for c in STRUCTURE_EARNINGS:
        if not frappe.db.exists("Salary Component", c):
            report.append(f"  ! Component `{c}` missing -- abort")
            return
        earnings_rows.append({"salary_component": c})

    deductions_rows = []
    for c in STRUCTURE_DEDUCTIONS:
        if not frappe.db.exists("Salary Component", c):
            report.append(f"  ! Component `{c}` missing -- abort")
            return
        deductions_rows.append({"salary_component": c})

    doc = frappe.get_doc({
        "doctype": "Salary Structure",
        "name": STRUCTURE_NAME,
        "is_active": "Yes",
        "company": COMPANY,
        "payroll_frequency": "Monthly",
        "currency": "NGN",
        "earnings": earnings_rows,
        "deductions": deductions_rows,
    }).insert(ignore_permissions=True, ignore_if_duplicate=True)
    report.append(f"  + inserted `{doc.name}` ({len(earnings_rows)} earnings + {len(deductions_rows)} deductions)")
    report.append("")


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def detect_company() -> str | None:
    rows = frappe.get_all("Company", fields=["name"], limit=2)
    return rows[0]["name"] if rows else None


def main():
    global COMPANY
    COMPANY = detect_company()

    print("=" * 72)
    print(f" Phase 6 / Step 2c.1 -- HMO model + Salary Structure (DRY_RUN={DRY_RUN})")
    print(f" Site: {frappe.local.site} | Company: {COMPANY}")
    print("=" * 72)

    report: list[str] = []
    report.append("# Step 2c.1 -- HMO model + Salary Structure")
    report.append("")
    report.append(f"_Generated: {frappe.utils.now_datetime()}_  ")
    report.append(f"_Site: {frappe.local.site} | DRY_RUN={DRY_RUN}_")
    report.append("")

    seed_hmo_custom_fields(report)
    update_medical_allowance(report)
    fix_paye_flag(report)
    add_hmo_topup_component(report)
    backfill_hmo_defaults(report)
    upsert_salary_structure(report)

    report.append("## 6. Next sub-steps before live June 25 payroll")
    report.append("")
    report.append("- [ ] **Step 2c.2** -- map each Salary Component to a GL Account in your CoA (so Payroll Entry posts cleanly).")
    report.append("- [ ] **Step 2c.3** -- create 217 Salary Structure Assignments with `base = April 2026 gross`.")
    report.append("- [ ] Replace placeholder ₦8,666 with real per-employee HMO premiums (HR backfill).")
    report.append("- [ ] Replace PAYE STUB with confirmed NTAA 2025 law.")
    report.append("")

    if not DRY_RUN:
        frappe.db.commit()

    p = Path("/tmp/step2c_hmo_structure.md")
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
