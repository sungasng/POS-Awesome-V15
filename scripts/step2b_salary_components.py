"""
Phase 6 / Step 2b: Salary Components master.

Creates 12 Salary Components for monthly payroll:

  EARNINGS (5)
    Basic Pay              BS        base * 0.40
    Transport Allowance    TA        base * 0.25
    Housing Allowance      HA        base * 0.25
    Cost of Living Allow.  COLA      base * 0.10
    Medical Allowance      MA        flat 8,666.00

  DEDUCTIONS (7)
    NSITF                  NSITF     base * 0.01            (informational, employer cost)
    Pension Employee       PEN-EE    (BS+HA+TA) * 0.08
    Pension Employer       PEN-ER    (BS+HA+TA) * 0.10      (informational, employer cost)
    PAYE                   PAYE      *** STUB *** NTAA 2025 Option A (REVIEW BEFORE GO-LIVE)
    Loan Repayment         LOAN-RP   manual amount per slip
    COOP Loan Repayment    COOP-LN   manual amount per slip
    Cooperative Contrib.   COOP-CN   manual amount per slip

Also:
  - converts Employee.state_of_residence to a Select with 6 NG states
    (Lagos, Edo, Delta, Rivers, Ogun, Oyo).

Idempotent. Toggle DRY_RUN=True to preview.

Output: /tmp/step2b_components.md

Run:
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/feat/sungas-customizations/scripts/step2b_salary_components.py" -o /tmp/step2b_salary_components.py
    bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/step2b_salary_components.py').read())"
"""

from __future__ import annotations

from pathlib import Path

import frappe


DRY_RUN = False
COMPANY = None  # auto-detected

# ---------------------------------------------------------------------------
# PAYE NTAA 2025 STUB FORMULA  (Option A)
# ---------------------------------------------------------------------------
# NB: bands per consensus reading of Nigeria Tax Act 2025 (effective 1 Jan 2026):
#   First 800,000           : 0%
#   Next  2,200,000 (->3M)  : 15%
#   Next  9,000,000 (->12M) : 18%
#   Next 13,000,000 (->25M) : 21%
#   Next 25,000,000 (->50M) : 23%
#   Above 50M               : 25%
#
# Stub assumption: flat 500,000 Rent Relief applied annually.  REPLACE WITH
# ACTUAL EMPLOYEE RENT RELIEF (lesser of 500K or 20% * annual rent paid) BEFORE
# JUNE 25 GO-LIVE.
# ---------------------------------------------------------------------------
PAYE_FORMULA = (
    # === STUB: NTAA 2025 PAYE (Option A) -- single-expression ternary chain ===
    # Annual taxable income = annual gross - 500K Rent Relief (placeholder).
    # Bands evaluated against annual taxable, result divided by 12 for monthly PAYE.
    #
    # Pre-computed cumulative tax at each band ceiling:
    #   B0 ≤ 800K   ->         0
    #   B1 ≤ 3M     -> (t-800K)*15%
    #   B2 ≤ 12M    -> 330K   + (t-3M)*18%
    #   B3 ≤ 25M    -> 1.95M  + (t-12M)*21%
    #   B4 ≤ 50M    -> 4.68M  + (t-25M)*23%
    #   B5 > 50M    -> 10.43M + (t-50M)*25%
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


# ---------------------------------------------------------------------------
# Component definitions
# ---------------------------------------------------------------------------

COMPONENTS = [
    # ---- Earnings ----
    {
        "name": "Basic Pay", "abbr": "BS", "type": "Earning",
        "formula": "base * 0.40",
        "is_tax_applicable": 1, "depends_on_payment_days": 1,
        "do_not_include_in_total": 0,
    },
    {
        "name": "Transport Allowance", "abbr": "TA", "type": "Earning",
        "formula": "base * 0.25",
        "is_tax_applicable": 1, "depends_on_payment_days": 1,
        "do_not_include_in_total": 0,
    },
    {
        "name": "Housing Allowance", "abbr": "HA", "type": "Earning",
        "formula": "base * 0.25",
        "is_tax_applicable": 1, "depends_on_payment_days": 1,
        "do_not_include_in_total": 0,
    },
    {
        "name": "Cost of Living Allowance", "abbr": "COLA", "type": "Earning",
        "formula": "base * 0.10",
        "is_tax_applicable": 1, "depends_on_payment_days": 1,
        "do_not_include_in_total": 0,
    },
    {
        "name": "Medical Allowance", "abbr": "MA", "type": "Earning",
        "formula": "8666",
        "is_tax_applicable": 0, "depends_on_payment_days": 0,
        "do_not_include_in_total": 0,
    },
    # ---- Deductions ----
    {
        "name": "NSITF", "abbr": "NSITF", "type": "Deduction",
        "formula": "base * 0.01",
        "is_tax_applicable": 0, "depends_on_payment_days": 0,
        # Employer cost -- excluded from employee Net Pay
        "do_not_include_in_total": 1,
        "statistical_component": 1,
    },
    {
        "name": "Pension Employee", "abbr": "PEN-EE", "type": "Deduction",
        "formula": "(BS + HA + TA) * 0.08",
        "is_tax_applicable": 0, "depends_on_payment_days": 0,
        "do_not_include_in_total": 0,
    },
    {
        "name": "Pension Employer", "abbr": "PEN-ER", "type": "Deduction",
        "formula": "(BS + HA + TA) * 0.10",
        "is_tax_applicable": 0, "depends_on_payment_days": 0,
        # Employer cost -- excluded from employee Net Pay
        "do_not_include_in_total": 1,
        "statistical_component": 1,
    },
    {
        "name": "PAYE", "abbr": "PAYE", "type": "Deduction",
        "formula": PAYE_FORMULA,
        "is_tax_applicable": 0, "depends_on_payment_days": 0,
        # Note: NOT using variable_based_on_taxable_salary -- that flag requires
        # an Income Tax Slab doctype and forbids custom formulas. Our self-contained
        # NTAA 2025 stub lives entirely in the formula field instead.
        "do_not_include_in_total": 0,
    },
    {
        "name": "Loan Repayment", "abbr": "LOAN-RP", "type": "Deduction",
        "formula": None,  # manual amount per slip
        "is_tax_applicable": 0, "depends_on_payment_days": 0,
        "do_not_include_in_total": 0,
    },
    {
        "name": "COOP Loan Repayment", "abbr": "COOP-LN", "type": "Deduction",
        "formula": None,  # manual
        "is_tax_applicable": 0, "depends_on_payment_days": 0,
        "do_not_include_in_total": 0,
    },
    {
        "name": "Cooperative Contribution", "abbr": "COOP-CN", "type": "Deduction",
        "formula": None,  # manual
        "is_tax_applicable": 0, "depends_on_payment_days": 0,
        "do_not_include_in_total": 0,
    },
]


NG_STATES_FOR_PAYROLL = [
    "Lagos", "Edo", "Delta", "Rivers", "Ogun", "Oyo",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def detect_company() -> str | None:
    rows = frappe.get_all("Company", fields=["name"], limit=2)
    return rows[0]["name"] if rows else None


def upsert_salary_component(spec: dict, report: list[str]) -> None:
    name = spec["name"]
    fields_to_set = {
        "salary_component": name,
        "salary_component_abbr": spec["abbr"],
        "type": spec["type"],
        "depends_on_payment_days": spec.get("depends_on_payment_days", 0),
        "is_tax_applicable": spec.get("is_tax_applicable", 0),
        "do_not_include_in_total": spec.get("do_not_include_in_total", 0),
        "statistical_component": spec.get("statistical_component", 0),
        "variable_based_on_taxable_salary":
            spec.get("variable_based_on_taxable_salary", 0),
    }
    formula = spec.get("formula")
    if formula:
        fields_to_set["amount_based_on_formula"] = 1
        # multi-line stub stored in `condition_and_formula_help` style via formula
        fields_to_set["formula"] = formula
    else:
        fields_to_set["amount_based_on_formula"] = 0
        fields_to_set["formula"] = None

    if frappe.db.exists("Salary Component", name):
        if DRY_RUN:
            report.append(f"  ~ would-update `{name}` ({spec['abbr']})")
            return
        doc = frappe.get_doc("Salary Component", name)
        changed = False
        for k, v in fields_to_set.items():
            if doc.get(k) != v:
                doc.set(k, v)
                changed = True
        if changed:
            doc.save(ignore_permissions=True)
            report.append(f"  ~ updated `{name}` ({spec['abbr']})")
        else:
            report.append(f"  = `{name}` ({spec['abbr']}) -- no changes")
        return

    if DRY_RUN:
        report.append(f"  + would-insert `{name}` ({spec['abbr']}, {spec['type']})")
        return
    doc = frappe.get_doc({
        "doctype": "Salary Component",
        **fields_to_set,
    })
    doc.insert(ignore_permissions=True, ignore_if_duplicate=True)
    report.append(f"  + inserted `{doc.name}` ({spec['abbr']}, {spec['type']})")


def convert_state_of_residence_to_select(report: list[str]) -> None:
    cf_name = "Employee-state_of_residence"
    if not frappe.db.exists("Custom Field", cf_name):
        report.append("  ! Custom Field not found (run Step 2a first)")
        return
    doc = frappe.get_doc("Custom Field", cf_name)
    desired_options = "\n".join([""] + NG_STATES_FOR_PAYROLL)
    desired_type = "Select"
    if doc.fieldtype == desired_type and doc.options == desired_options:
        report.append("  = already a Select with the 6 states")
        return
    if DRY_RUN:
        report.append(f"  ~ would-convert {cf_name} -> Select [{', '.join(NG_STATES_FOR_PAYROLL)}]")
        return
    doc.fieldtype = desired_type
    doc.options = desired_options
    doc.save(ignore_permissions=True)
    report.append(f"  ~ converted {cf_name} -> Select [{', '.join(NG_STATES_FOR_PAYROLL)}]")


def smoke_test(report: list[str]) -> None:
    """Compute monthly figures for a fictitious base = 200,000 to verify formulas."""
    base = 200_000.0
    BS = base * 0.40
    TA = base * 0.25
    HA = base * 0.25
    COLA = base * 0.10
    MA = 8_666.0
    GROSS = BS + TA + HA + COLA + MA  # for display only

    PEN_EE = (BS + HA + TA) * 0.08
    PEN_ER = (BS + HA + TA) * 0.10
    NSITF = base * 0.01

    annual_gross = GROSS * 12
    annual_taxable = max(0, annual_gross - 500000)
    if annual_taxable <= 800000:
        annual_tax = 0
    elif annual_taxable <= 3000000:
        annual_tax = (annual_taxable - 800000) * 0.15
    elif annual_taxable <= 12000000:
        annual_tax = 2_200_000 * 0.15 + (annual_taxable - 3_000_000) * 0.18
    elif annual_taxable <= 25000000:
        annual_tax = (2_200_000 * 0.15 + 9_000_000 * 0.18 +
                      (annual_taxable - 12_000_000) * 0.21)
    elif annual_taxable <= 50000000:
        annual_tax = (2_200_000 * 0.15 + 9_000_000 * 0.18 +
                      13_000_000 * 0.21 + (annual_taxable - 25_000_000) * 0.23)
    else:
        annual_tax = (2_200_000 * 0.15 + 9_000_000 * 0.18 +
                      13_000_000 * 0.21 + 25_000_000 * 0.23 +
                      (annual_taxable - 50_000_000) * 0.25)
    PAYE = annual_tax / 12

    NET = GROSS - PEN_EE - PAYE  # NSITF + PEN_ER excluded (statistical)

    report.append(f"_Fictitious base = ₦{base:,.0f}/month_")
    report.append("")
    report.append("| Component | Amount (₦) |")
    report.append("|---|---:|")
    for label, val in [
        ("Basic (40%)", BS), ("Transport (25%)", TA), ("Housing (25%)", HA),
        ("COLA (10%)", COLA), ("Medical (flat)", MA),
        ("**Gross**", GROSS),
        ("Pension EE (8% of BHT)", PEN_EE),
        ("PAYE (NTAA 2025 STUB)", PAYE),
        ("**Net Pay**", NET),
        ("_NSITF (1%, employer cost, informational)_", NSITF),
        ("_Pension ER (10% of BHT, employer cost, informational)_", PEN_ER),
    ]:
        report.append(f"| {label} | {val:,.2f} |")
    report.append("")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    global COMPANY
    COMPANY = detect_company()

    print("=" * 72)
    print(f" Phase 6 / Step 2b -- Salary Components (DRY_RUN={DRY_RUN})")
    print(f" Site: {frappe.local.site} | Company: {COMPANY}")
    print("=" * 72)

    report: list[str] = []
    report.append("# Step 2b -- Salary Components master")
    report.append("")
    report.append(f"_Generated: {frappe.utils.now_datetime()}_  ")
    report.append(f"_Site: {frappe.local.site} | DRY_RUN={DRY_RUN}_")
    report.append("")

    report.append("## 1. Salary Components")
    report.append("")
    for spec in COMPONENTS:
        upsert_salary_component(spec, report)
    report.append("")

    report.append("## 2. Employee.state_of_residence -> Select picklist")
    report.append("")
    convert_state_of_residence_to_select(report)
    report.append("")

    report.append("## 3. Smoke test (sanity-check formulas)")
    report.append("")
    smoke_test(report)

    report.append("## 4. Open items before live payroll (June 25)")
    report.append("")
    report.append("- [ ] **PAYE STUB** -- replace Option A NTAA 2025 bands with confirmed law before submitting live payroll.")
    report.append("- [ ] **Rent Relief** -- replace flat ₦500K with actual per-employee value (lesser of ₦500K or 20% * annual rent paid).")
    report.append("- [ ] **GL accounts** -- wire each Salary Component to a Cost Center / Account via Salary Component > Accounts table (Step 2c).")
    report.append("- [ ] **Salary Structure** -- single structure linking all 12 components (Step 2c).")
    report.append("- [ ] **Salary Structure Assignment** -- assign each of 217 employees with their base = April gross (Step 2c).")
    report.append("")

    if not DRY_RUN:
        frappe.db.commit()

    p = Path("/tmp/step2b_components.md")
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
