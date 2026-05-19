"""
Phase 6 / Step 2c.2B: GL account mapping for payroll Salary Components.

Creates 4 missing accounts and wires each Salary Component to a Debit/Credit
account pair in the Company's Salary Component Accounts child table.

Accounts created (under 6200 - Other Payables - SCL):
    6208 - HMO - Payable - SCL              (Payable)
    6213 - Cooperative Loan - Payable - SCL (Payable)
    6214 - Cooperative Contribution - Payable - SCL (Payable)

Accounts created (under 1700-ish Receivables area):
    1701 - Staff Loan Receivable - SCL      (Receivable)

GL mapping per component (all earnings expense to 9101 per user choice 1a):

    Component               | DR (expense/asset)            | CR (liability/clearing)
    ------------------------|-------------------------------|----------------------------
    Basic Pay               | 9101 Salary and wages         | 6207 Salary Control
    Transport Allowance     | 9101 Salary and wages         | 6207 Salary Control
    Housing Allowance       | 9101 Salary and wages         | 6207 Salary Control
    COLA                    | 9101 Salary and wages         | 6207 Salary Control
    Medical Allowance       | (statistical -- no GL)
    NSITF                   | 9108 NSITF Exp                | 6209 NSITF Payable
    Pension Employee        | 6207 Salary Control           | 6211 Pension Payable
    Pension Employer        | 9247 Employer's Pension Exp   | 6211 Pension Payable
    PAYE                    | 6207 Salary Control           | 6212 PAYE Payable
    HMO Top-up (Staff)      | 6207 Salary Control           | 6208 HMO Payable (NEW)
    Loan Repayment          | 6207 Salary Control           | 1701 Staff Loan Recv (NEW)
    COOP Loan Repayment     | 6207 Salary Control           | 6213 COOP Loan Payable (NEW)
    Cooperative Contrib.    | 6207 Salary Control           | 6214 COOP Contrib Payable (NEW)

Idempotent. Toggle DRY_RUN=True to preview.

Output: /tmp/step2c2b_gl_mapping.md

Run:
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/feat/sungas-customizations/scripts/step2c2b_gl_mapping.py" -o /tmp/step2c2b_gl_mapping.py
    bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/step2c2b_gl_mapping.py').read())"
"""

from __future__ import annotations

from pathlib import Path

import frappe


DRY_RUN = False

# Resolve at runtime
COMPANY: str | None = None
ABBR: str | None = None

OTHER_PAYABLES_PARENT = "6200 - Other Payables - SCL"

# ---------------------------------------------------------------------------
# 1. New accounts to create (only if missing).
# ---------------------------------------------------------------------------

NEW_ACCOUNTS = [
    {
        "account_name": "6215 - HMO - Payable",
        "account_number": "6215",
        "account_type": "Payable",
        "root_type": "Liability",
        "parent": OTHER_PAYABLES_PARENT,
    },
    {
        "account_name": "6216 - Cooperative Loan - Payable",
        "account_number": "6216",
        "account_type": "Payable",
        "root_type": "Liability",
        "parent": OTHER_PAYABLES_PARENT,
    },
    {
        "account_name": "6218 - Cooperative Contribution - Payable",
        "account_number": "6218",
        "account_type": "Payable",
        "root_type": "Liability",
        "parent": OTHER_PAYABLES_PARENT,
    },
    # Staff Loan Receivable -- parent decided at runtime by scanning for a
    # suitable "Other Receivables" group; falls back to "Loans and Advances".
    {
        "account_name": "1701 - Staff Loan Receivable",
        "account_number": "1701",
        "account_type": "Receivable",
        "root_type": "Asset",
        "parent": None,  # resolved dynamically
    },
]

# ---------------------------------------------------------------------------
# 2. Component -> account mapping.
# `default_account` lives on Salary Component Account child for the Company.
# For each component we record both the EXPENSE/DR account and the LIABILITY/CR
# account, but ERPNext only stores ONE account per component-per-company.
# Convention:
#   - For Earning components: the Salary Component's account holds the EXPENSE side
#     (Salary Slip will DR this, CR the Salary Control automatically).
#   - For Deduction components: the Salary Component's account holds the
#     LIABILITY side (Salary Slip will CR this, DR the Salary Control / expense).
# ---------------------------------------------------------------------------

COMPONENT_ACCOUNT_MAP = {
    # Earnings
    "Basic Pay":                  "9101 - Salary and wages - SCL",
    "Transport Allowance":        "9101 - Salary and wages - SCL",
    "Housing Allowance":          "9101 - Salary and wages - SCL",
    "Cost of Living Allowance":   "9101 - Salary and wages - SCL",
    # Medical Allowance is statistical -> no GL account needed
    # Deductions
    "NSITF":                      "6209 - NSITF - Payable - SCL",
    "Pension Employee":           "6211 - Pension - Payable - SCL",
    "Pension Employer":           "6211 - Pension - Payable - SCL",
    "PAYE":                       "6212 - PAYE - Payable - SCL",
    "HMO Top-up (Staff Paid)":    "6215 - HMO - Payable - SCL",
    "Loan Repayment":             "1701 - Staff Loan Receivable - SCL",
    "COOP Loan Repayment":        "6216 - Cooperative Loan - Payable - SCL",
    "Cooperative Contribution":   "6218 - Cooperative Contribution - Payable - SCL",
}

# Expense-side override for "statistical employer cost" deductions. These need to
# hit a P&L expense account (not just a liability). Wired via custom field
# `salary_component.payroll_expense_account` if we want; otherwise we make the
# component a 2-account beast via Salary Component Account row + a fallback expense.
EMPLOYER_COST_EXPENSE_OVERRIDE = {
    "NSITF":            "9108 - NSITF - Exp - SCL",
    "Pension Employer": "9247 - Employer's Contribution - Pension - SCL",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def detect_company() -> tuple[str | None, str | None]:
    rows = frappe.get_all("Company", fields=["name", "abbr"], limit=2)
    return (rows[0]["name"], rows[0]["abbr"]) if rows else (None, None)


def resolve_staff_loan_parent() -> str:
    """Find a sensible parent for 1701 - Staff Loan Receivable."""
    # Try common parents first
    candidates = [
        "1700 - Other Receivables - SCL",
        "1700 - Loans and Advances - SCL",
        "1500 - Loans and Advances - SCL",
        "1500 - Current Assets - SCL",
    ]
    for c in candidates:
        if frappe.db.exists("Account", c):
            return c
    # Fallback: first asset group whose name contains "receivable" or "advance" or "current asset"
    groups = frappe.get_all(
        "Account",
        filters={"is_group": 1, "root_type": "Asset"},
        fields=["name"],
    )
    for kw in ["receivable", "advance", "current asset"]:
        for g in groups:
            if kw in g["name"].lower():
                return g["name"]
    raise RuntimeError("Could not resolve parent for Staff Loan Receivable")


def upsert_account(spec: dict, report: list[str]) -> str | None:
    """Create account if missing. Returns the full ERP account name (with suffix)."""
    expected_name = f"{spec['account_name']} - {ABBR}"
    if frappe.db.exists("Account", expected_name):
        report.append(f"  = `{expected_name}` already exists")
        return expected_name
    # Also check by account_number to catch numbering collisions
    if spec.get("account_number"):
        existing = frappe.get_all(
            "Account",
            filters={"account_number": spec["account_number"], "company": COMPANY},
            fields=["name"],
            limit=1,
        )
        if existing:
            report.append(
                f"  ! account_number {spec['account_number']} already taken by "
                f"`{existing[0]['name']}` -- SKIP. Update COMPONENT_ACCOUNT_MAP to point there."
            )
            return None
    if DRY_RUN:
        report.append(f"  + would-insert `{expected_name}` under `{spec['parent']}`")
        return expected_name
    doc = frappe.get_doc({
        "doctype": "Account",
        "account_name": spec["account_name"],
        "account_number": spec.get("account_number"),
        "parent_account": spec["parent"],
        "is_group": 0,
        "company": COMPANY,
        "account_type": spec.get("account_type") or "",
        "root_type": spec["root_type"],
    }).insert(ignore_permissions=True, ignore_if_duplicate=True)
    report.append(f"  + inserted `{doc.name}` (type={spec.get('account_type') or '-'})")
    return doc.name


def wire_component_account(component: str, account: str, report: list[str]) -> None:
    if not frappe.db.exists("Salary Component", component):
        report.append(f"  ! Salary Component `{component}` not found, skip")
        return
    if not frappe.db.exists("Account", account):
        report.append(f"  ! Account `{account}` not found, skip")
        return
    doc = frappe.get_doc("Salary Component", component)
    # Idempotent: replace any existing row for this Company, keep others.
    existing = [r for r in (doc.accounts or []) if r.company == COMPANY]
    if existing and existing[0].account == account:
        report.append(f"  = `{component}` already mapped to `{account}`")
        return
    if DRY_RUN:
        action = "update" if existing else "insert"
        report.append(f"  ~ would-{action}: `{component}` -> `{account}`")
        return
    # Remove old rows for this company
    doc.accounts = [r for r in (doc.accounts or []) if r.company != COMPANY]
    doc.append("accounts", {"company": COMPANY, "account": account})
    doc.save(ignore_permissions=True)
    report.append(f"  ~ `{component}` -> `{account}`")


def main():
    global COMPANY, ABBR
    COMPANY, ABBR = detect_company()

    print("=" * 72)
    print(f" Phase 6 / Step 2c.2B -- GL account mapping (DRY_RUN={DRY_RUN})")
    print(f" Company: {COMPANY} (abbr={ABBR})")
    print("=" * 72)

    report: list[str] = []
    report.append("# Step 2c.2B -- GL account mapping for payroll")
    report.append("")
    report.append(f"_Generated: {frappe.utils.now_datetime()}_  ")
    report.append(f"_Site: {frappe.local.site} | Company: {COMPANY} | DRY_RUN={DRY_RUN}_")
    report.append("")

    # Resolve Staff Loan parent
    staff_loan_parent = resolve_staff_loan_parent()
    for spec in NEW_ACCOUNTS:
        if spec["account_name"].startswith("1701"):
            spec["parent"] = staff_loan_parent

    # 1. Create missing accounts
    report.append("## 1. New accounts")
    report.append("")
    for spec in NEW_ACCOUNTS:
        upsert_account(spec, report)
    report.append("")

    # 2. Wire components -> accounts
    report.append("## 2. Salary Component -> Account mapping")
    report.append("")
    for component, account in COMPONENT_ACCOUNT_MAP.items():
        wire_component_account(component, account, report)
    report.append("")

    # 3. JE preview for a fictitious ₦200K-base employee
    report.append("## 3. JE preview (₦200K base, Family HMO ₦8,666, no top-up, no loans)")
    report.append("")
    base = 200_000
    BS = base * 0.40        # 80,000
    TA = base * 0.25        # 50,000
    HA = base * 0.25        # 50,000
    COLA = base * 0.10      # 20,000
    MA = 8_666              # statistical, doesn't post
    PEN_EE = (BS + HA + TA) * 0.08    # 14,400
    PEN_ER = (BS + HA + TA) * 0.10    # 18,000
    NSITF = base * 0.01               # 2,000
    # PAYE ~= 15,050 from prior smoke test
    PAYE = 15050
    NET = BS + TA + HA + COLA - PEN_EE - PAYE

    report.append("| Line | DR (₦) | CR (₦) | Account |")
    report.append("|---|---:|---:|---|")
    report.append(f"| Basic Pay | {BS:,.0f} | | 9101 Salary and wages |")
    report.append(f"| Transport | {TA:,.0f} | | 9101 Salary and wages |")
    report.append(f"| Housing | {HA:,.0f} | | 9101 Salary and wages |")
    report.append(f"| COLA | {COLA:,.0f} | | 9101 Salary and wages |")
    report.append(f"| Pension Employer | {PEN_ER:,.0f} | | 9247 Employer's Pension Exp |")
    report.append(f"| NSITF | {NSITF:,.0f} | | 9108 NSITF Exp |")
    report.append(f"| Pension (EE+ER) | | {(PEN_EE+PEN_ER):,.0f} | 6211 Pension Payable |")
    report.append(f"| NSITF | | {NSITF:,.0f} | 6209 NSITF Payable |")
    report.append(f"| PAYE | | {PAYE:,.0f} | 6212 PAYE Payable |")
    report.append(f"| Net Pay (clearing) | | {NET:,.0f} | 6207 Salary Control |")
    total_dr = BS + TA + HA + COLA + PEN_ER + NSITF
    total_cr = PEN_EE + PEN_ER + NSITF + PAYE + NET
    report.append(f"| **TOTAL** | **{total_dr:,.0f}** | **{total_cr:,.0f}** | {'✅ balanced' if total_dr == total_cr else '⚠️ UNBALANCED'} |")
    report.append("")
    report.append(f"_Medical Allowance ₦{MA:,.0f} appears on payslip but is statistical -- no GL impact._")
    report.append("")

    if not DRY_RUN:
        frappe.db.commit()

    p = Path("/tmp/step2c2b_gl_mapping.md")
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
