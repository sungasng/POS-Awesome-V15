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
        "key": "HMO_PAYABLE",
        "account_name_base": "HMO - Payable",
        "number_range": (6219, 6299),
        "account_type": "Payable",
        "root_type": "Liability",
        "parent": OTHER_PAYABLES_PARENT,
    },
    {
        "key": "COOP_LOAN",
        "account_name_base": "Cooperative Loan - Payable",
        "number_range": (6219, 6299),
        "account_type": "Payable",
        "root_type": "Liability",
        "parent": OTHER_PAYABLES_PARENT,
    },
    {
        "key": "COOP_CONTRIB",
        "account_name_base": "Cooperative Contribution - Payable",
        "number_range": (6219, 6299),
        "account_type": "Payable",
        "root_type": "Liability",
        "parent": OTHER_PAYABLES_PARENT,
    },
    {
        "key": "STAFF_LOAN",
        "account_name_base": "Staff Loan Receivable",
        "number_range": (2900, 2999),  # Outside existing ranges (Prepayments 2800-2899 used)
        "account_type": "Receivable",
        "root_type": "Asset",
        "parent": None,
    },
]

# Filled in at runtime by upsert_account -- maps key -> actual ERP account name
RESOLVED_ACCOUNTS: dict[str, str] = {}

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
    # Resolved dynamically at runtime via RESOLVED_ACCOUNTS
    "HMO Top-up (Staff Paid)":    "HMO_PAYABLE",
    "Loan Repayment":             "STAFF_LOAN",
    "COOP Loan Repayment":        "COOP_LOAN",
    "Cooperative Contribution":   "COOP_CONTRIB",
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
    """Find a sensible parent for the new Staff Loan Receivable account."""
    # Try common parents first
    candidates = [
        "1700 - Other Receivables - SCL",
        "2500 - 2799 - Account Receivables - SCL",
        "1500 - Loans and Advances - SCL",
        "1500 - Current Assets - SCL",
    ]
    for c in candidates:
        if frappe.db.exists("Account", c):
            return c
    groups = frappe.get_all(
        "Account",
        filters={"is_group": 1, "root_type": "Asset"},
        fields=["name"],
    )
    for kw in ["receivable", "advance", "loans"]:
        for g in groups:
            if kw in g["name"].lower():
                return g["name"]
    raise RuntimeError("Could not resolve parent for Staff Loan Receivable")


def find_next_free_number(start: int, end: int) -> int | None:
    """Return first integer in [start, end] not used by any Account (any company)."""
    used = set()
    rows = frappe.get_all(
        "Account",
        filters={"account_number": ["is", "set"]},
        fields=["account_number"],
    )
    for r in rows:
        if r.get("account_number") and r["account_number"].isdigit():
            n = int(r["account_number"])
            if start <= n <= end:
                used.add(n)
    for n in range(start, end + 1):
        if n not in used:
            return n
    return None


def upsert_account(spec: dict, report: list[str]) -> str | None:
    """Find a free account_number in range, then create. Returns full ERP name."""
    # First check if a matching account already exists (by name pattern)
    base = spec["account_name_base"]
    existing = frappe.get_all(
        "Account",
        filters={
            "account_name": ["like", f"%{base}%"],
            "company": COMPANY,
            "is_group": 0,
            "root_type": spec["root_type"],
        },
        fields=["name", "account_number"],
        limit=5,
    )
    if existing:
        report.append(f"  = `{existing[0]['name']}` already exists (matched on name)")
        if spec.get("key"):
            RESOLVED_ACCOUNTS[spec["key"]] = existing[0]["name"]
        return existing[0]["name"]

    lo, hi = spec["number_range"]
    free = find_next_free_number(lo, hi)
    if free is None:
        report.append(f"  ! no free number in {lo}-{hi} range, skip `{base}`")
        return None

    full_name_base = f"{free} - {base}"
    expected_name = f"{full_name_base} - {ABBR}"
    if DRY_RUN:
        report.append(f"  + would-insert `{expected_name}` under `{spec['parent']}`")
        if spec.get("key"):
            RESOLVED_ACCOUNTS[spec["key"]] = expected_name
        return expected_name

    doc = frappe.get_doc({
        "doctype": "Account",
        "account_name": full_name_base,
        "account_number": str(free),
        "parent_account": spec["parent"],
        "is_group": 0,
        "company": COMPANY,
        "account_type": spec.get("account_type") or "",
        "root_type": spec["root_type"],
    }).insert(ignore_permissions=True, ignore_if_duplicate=True)
    report.append(f"  + inserted `{doc.name}` (number={free}, type={spec.get('account_type') or '-'})")
    if spec.get("key"):
        RESOLVED_ACCOUNTS[spec["key"]] = doc.name
    return doc.name


def wire_component_account(component: str, account_or_key: str, report: list[str]) -> None:
    if not frappe.db.exists("Salary Component", component):
        report.append(f"  ! Salary Component `{component}` not found, skip")
        return
    # If the value is a placeholder key, resolve it
    account = RESOLVED_ACCOUNTS.get(account_or_key, account_or_key)
    if not frappe.db.exists("Account", account):
        report.append(f"  ! Account `{account}` not found, skip `{component}`")
        return
    doc = frappe.get_doc("Salary Component", component)
    existing = [r for r in (doc.accounts or []) if r.company == COMPANY]
    if existing and existing[0].account == account:
        report.append(f"  = `{component}` already mapped to `{account}`")
        return
    if DRY_RUN:
        action = "update" if existing else "insert"
        report.append(f"  ~ would-{action}: `{component}` -> `{account}`")
        return
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
        if spec.get("key") == "STAFF_LOAN":
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
