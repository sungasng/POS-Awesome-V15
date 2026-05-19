"""
Phase 6 / Step 3: PAYE under NTAA 2025 (effective 2026-01-01).

Idempotent. Toggle DRY_RUN=True to preview.

Sections:
  1. Add Employee.rent_paid_annually custom field (Currency, default 0)
  2. Update PAYE Salary Component:
     - condition: excludes Non-Executive/Chairman/Independent Directors
     - formula: NTAA 2025 brackets on annualised taxable income
                taxable = max(0, gross*12 - min(rent*0.20, 500000) - pension_ee*12)
  3. Python-side dry-run validation against 5 sample base values

Run:
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/feat/sungas-customizations/scripts/step3_paye_ntaa2025.py" -o /tmp/step3.py
    bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/step3.py').read())"
"""

from __future__ import annotations
from pathlib import Path
import frappe


DRY_RUN = False


# ---------------------------------------------------------------------------
# NTAA 2025 brackets (annual, NGN)
# ---------------------------------------------------------------------------
NTAA_BRACKETS = [
    # (upper, base_tax, marginal_rate)
    (   800_000,            0, 0.00),
    ( 3_000_000,            0, 0.15),
    (12_000_000,      330_000, 0.18),  # 330k = 2.2M * 0.15
    (25_000_000,    1_950_000, 0.21),  # 1.95M = 330k + 9M * 0.18
    (50_000_000,    4_680_000, 0.23),  # 4.68M = 1.95M + 13M * 0.21
    (float("inf"), 10_430_000, 0.25),  # 10.43M = 4.68M + 25M * 0.23
]


def compute_paye_annual(taxable: float) -> float:
    """NTAA 2025 annual PAYE on taxable income."""
    prev_upper = 0
    for upper, base_tax, rate in NTAA_BRACKETS:
        if taxable <= upper:
            return base_tax + (taxable - prev_upper) * rate
        prev_upper = upper
    return 0.0  # unreachable


def compute_monthly_paye(gross_monthly: float, rent_annual: float = 0, pension_ee_monthly: float = 0) -> dict:
    """Python-side reference implementation."""
    annual_gross = gross_monthly * 12
    rent_relief = min(0.20 * rent_annual, 500_000)
    annual_pension_ee = pension_ee_monthly * 12
    taxable = max(0, annual_gross - rent_relief - annual_pension_ee)
    annual_tax = compute_paye_annual(taxable)
    return {
        "annual_gross": annual_gross,
        "rent_relief": rent_relief,
        "annual_pension_ee": annual_pension_ee,
        "taxable": taxable,
        "annual_tax": annual_tax,
        "monthly_paye": annual_tax / 12,
        "effective_rate_pct": (annual_tax / annual_gross * 100) if annual_gross else 0,
    }


# ---------------------------------------------------------------------------
# Frappe Salary Component formula (single expression, safe_eval compatible)
# Variables in scope (Salary Slip formula context):
#   gross_pay  -> sum of earnings on this slip
#   PEN_EE     -> Pension Employee deduction amount (hyphen in abbr -> underscore)
#   employee   -> Employee doc (we use .rent_paid_annually)
#
# Future-ready: add  (NHF or 0)*12  and  (LIFE or 0)*12  to the subtraction
# in `T` once those components exist on the structure.
# ---------------------------------------------------------------------------

# T = annual taxable income, computed inline (safe_eval doesn't allow walrus)
_T = "max(0, gross_pay*12 - min(0.20 * (employee.rent_paid_annually or 0), 500000) - (PEN_EE or 0) * 12)"

PAYE_FORMULA = (
    f"(0 if {_T} <= 800000 "
    f"else ({_T} - 800000) * 0.15 if {_T} <= 3000000 "
    f"else 330000 + ({_T} - 3000000) * 0.18 if {_T} <= 12000000 "
    f"else 1950000 + ({_T} - 12000000) * 0.21 if {_T} <= 25000000 "
    f"else 4680000 + ({_T} - 25000000) * 0.23 if {_T} <= 50000000 "
    f"else 10430000 + ({_T} - 50000000) * 0.25) / 12"
)

# Exclude Non-Executive Directors / Chairman / Independent Directors (10% WHT, not PAYE)
PAYE_CONDITION = (
    "(employee.designation or '').lower().strip() not in "
    "('chairman', 'non-executive director', 'non executive director', 'independent director')"
)


# ---------------------------------------------------------------------------
# 1. Custom field
# ---------------------------------------------------------------------------

def add_rent_field(report: list[str]) -> None:
    report.append("## 1. Custom field Employee.rent_paid_annually")
    report.append("")
    cf_name = "Employee-rent_paid_annually"
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
        "fieldname": "rent_paid_annually",
        "label": "Annual Rent Paid (₦)",
        "fieldtype": "Currency",
        "default": "0",
        "insert_after": "payroll_cost_center",
        "description": (
            "Annual rent declared by employee. Used to compute Rent Relief "
            "under NTAA 2025 (20% of rent, capped at ₦500,000)."
        ),
    }).insert(ignore_permissions=True, ignore_if_duplicate=True)
    report.append("  + inserted (default = 0)")
    report.append("")


# ---------------------------------------------------------------------------
# 2. Update PAYE Salary Component
# ---------------------------------------------------------------------------

def update_paye_component(report: list[str]) -> None:
    report.append("## 2. Update PAYE Salary Component (NTAA 2025)")
    report.append("")
    if not frappe.db.exists("Salary Component", "PAYE"):
        report.append("  ! PAYE component NOT FOUND -- abort")
        return
    sc = frappe.get_doc("Salary Component", "PAYE")
    new_condition = PAYE_CONDITION
    new_formula = PAYE_FORMULA
    if sc.condition == new_condition and sc.formula == new_formula and sc.amount_based_on_formula:
        report.append("  = already up-to-date")
        report.append("")
        return
    if DRY_RUN:
        report.append("  + would-update")
        report.append("  proposed condition:")
        report.append(f"    {new_condition}")
        report.append("  proposed formula:")
        report.append(f"    {new_formula}")
        report.append("")
        return
    sc.amount_based_on_formula = 1
    sc.condition = new_condition
    sc.formula = new_formula
    sc.save(ignore_permissions=True)
    report.append("  + updated condition + formula")
    report.append("")


# ---------------------------------------------------------------------------
# 3. Python-side dry-run validation
# ---------------------------------------------------------------------------

def dry_run_samples(report: list[str]) -> None:
    report.append("## 3. Python-side validation -- expected PAYE for sample gross values")
    report.append("")
    report.append("  Assumptions: rent=₦0, pension_ee=8% of monthly gross (proxy)")
    report.append("")
    samples = [
        ("Min wage (₦70k/mo)",       70_000),
        ("Cleaner correct (₦39.8k)", 39_820.77),
        ("Cleaner CURRENT BAD",       3_982.08),   # 10x bug
        ("Cashier (~₦99k)",         99_372),
        ("Mid-tier (₦300k/mo)",    300_000),
        ("Senior (₦600k/mo)",      600_000),
        ("Manager (₦1M/mo)",     1_000_000),
        ("COO (₦1.75M/mo)",      1_747_200),
    ]
    report.append("  | Scenario                       |  Gross/mo |  Pension EE/mo |   Taxable/yr |   PAYE/mo |  Eff% |")
    report.append("  |--------------------------------|----------:|--------------:|-------------:|----------:|------:|")
    for label, g in samples:
        pen = g * 0.08
        r = compute_monthly_paye(g, rent_annual=0, pension_ee_monthly=pen)
        report.append(
            f"  | {label:30s} | {g:>9,.0f} | {pen:>13,.0f} | {r['taxable']:>12,.0f} | "
            f"{r['monthly_paye']:>9,.0f} | {r['effective_rate_pct']:>4.1f}% |"
        )
    report.append("")
    report.append("  NTAA 2025 reference brackets (annual):")
    report.append("    ₦0 – ₦800k          = 0%     (exempt)")
    report.append("    ₦800k – ₦3M         = 15%")
    report.append("    ₦3M – ₦12M          = 18%")
    report.append("    ₦12M – ₦25M         = 21%")
    report.append("    ₦25M – ₦50M         = 23%")
    report.append("    >₦50M               = 25%")
    report.append("")


# ---------------------------------------------------------------------------
# 4. Quick audit: flag suspiciously low SSA bases (potential 10x bug)
# ---------------------------------------------------------------------------

def audit_low_bases(report: list[str]) -> None:
    report.append("## 4. SSA base audit -- flag bases under ₦30,000/mo (NG min wage ~₦70k)")
    report.append("")
    rows = frappe.db.sql(
        """
        select e.name, e.employee_name, e.designation, e.department, e.branch, ssa.base
        from `tabSalary Structure Assignment` ssa
        join tabEmployee e on e.name = ssa.employee
        where ssa.salary_structure='Sungas Standard'
          and ssa.docstatus=1
          and ssa.base < 30000
        order by ssa.base
        """,
        as_dict=1,
    )
    if not rows:
        report.append("  ✅ No suspicious bases (none under ₦30k)")
        report.append("")
        return
    report.append(f"  ⚠ {len(rows)} employee(s) with base < ₦30,000 (likely 10x bug):")
    report.append("")
    report.append("  | Employee ID | Name                          | Designation         | Branch          |    Base/mo |")
    report.append("  |-------------|-------------------------------|---------------------|-----------------|-----------:|")
    for r in rows:
        report.append(
            f"  | {r['name']:11s} | {(r['employee_name'] or '')[:29]:29s} | "
            f"{(r['designation'] or '')[:19]:19s} | {(r['branch'] or '')[:15]:15s} | "
            f"{r['base']:>10,.2f} |"
        )
    report.append("")


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def main():
    print("=" * 72)
    print(f" Phase 6 / Step 3 -- PAYE NTAA 2025 (DRY_RUN={DRY_RUN})")
    print("=" * 72)

    report: list[str] = []
    report.append("# Step 3 -- PAYE under NTAA 2025")
    report.append("")
    report.append(f"_Generated: {frappe.utils.now_datetime()} | Site: {frappe.local.site} | DRY_RUN={DRY_RUN}_")
    report.append("")

    add_rent_field(report)
    update_paye_component(report)
    dry_run_samples(report)
    audit_low_bases(report)

    if not DRY_RUN:
        frappe.db.commit()

    p = Path("/tmp/step3_paye.md")
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
