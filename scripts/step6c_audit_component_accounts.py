"""
Phase 6 / Step 6c-AUDIT-2: verify Salary Component -> GL account mapping.

Read-only. No writes.

For each Salary Component used by `Sungas Standard`, prints the configured
"Account" (per Company) so we can confirm:

  - Earnings (Basic, Housing, Transport, Leave Allowance, 13th Month, etc.)
    are wired to an EXPENSE account like `9101 - Salary and wages - SCL`.

  - Statutory deductions (PAYE, Pension Employee, NHF, NHIS) are wired to
    LIABILITY/PAYABLE accounts (e.g. 6210/6211/6212).

Any earning that points to a Liability account, or any deduction that
points to an Expense account, will produce wrong GL entries on Salary
Slip submit. The script flags these.

Run:
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/feat/sungas-customizations/scripts/step6c_audit_component_accounts.py" -o /tmp/s6c_audit2.py
    bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/s6c_audit2.py').read())"
"""

from __future__ import annotations
from pathlib import Path
import frappe


COMPANY = "SUNGAS COMPANY LIMITED"
STRUCTURE = "Sungas Standard"


def main():
    print("=" * 72)
    print(f" Phase 6 / Step 6c-AUDIT-2 -- Salary Component GL Mapping ({STRUCTURE})")
    print("=" * 72)

    out: list[str] = []

    if not frappe.db.exists("Salary Structure", STRUCTURE):
        print(f"  ! Salary Structure {STRUCTURE!r} not found")
        return

    ss = frappe.get_doc("Salary Structure", STRUCTURE)
    components = []
    for row in ss.earnings:
        components.append((row.salary_component, "Earning"))
    for row in ss.deductions:
        components.append((row.salary_component, "Deduction"))

    out.append(f"# Salary Component -> Account audit ({STRUCTURE})")
    out.append("")
    out.append(f"_Generated: {frappe.utils.now_datetime()} | Site: {frappe.local.site}_")
    out.append("")
    out.append("| Component | Type | Mapped Account | Account root_type | Status |")
    out.append("|-----------|------|----------------|-------------------|--------|")

    issues = 0
    for comp_name, kind in components:
        # Pull the Salary Component flag (statistical components are slip-only, no GL)
        is_statistical = bool(frappe.db.get_value("Salary Component", comp_name, "statistical_component") or 0)

        # Salary Component has child table `accounts` with company + account
        account = frappe.db.get_value(
            "Salary Component Account",
            {"parent": comp_name, "company": COMPANY},
            "account",
        )

        # Statistical components are intentionally unmapped (company-borne, no GL post).
        if is_statistical:
            label = "STAT" if not account else f"STAT (mapped: {account})"
            out.append(f"| {comp_name} | {kind} (statistical) | _(none expected)_ | - | = {label} |")
            continue

        if not account:
            out.append(f"| {comp_name} | {kind} | _(none)_ | - | ! NO MAPPING |")
            issues += 1
            continue
        root_type = frappe.db.get_value("Account", account, "root_type")
        account_type = frappe.db.get_value("Account", account, "account_type") or "-"
        # Sanity rule
        bad = False
        reason = "OK"
        if kind == "Earning" and root_type != "Expense":
            bad = True
            reason = f"earning should hit Expense, got {root_type}"
        elif kind == "Deduction":
            # Statutory deductions should be Liability (Payable). Other deductions
            # like Cooperative loan recoveries can be Liability too. Asset is allowed
            # only for receivable-style deductions like Staff Loan recovery.
            if root_type not in ("Liability", "Asset"):
                bad = True
                reason = f"deduction should hit Liability/Asset, got {root_type}"
        if bad:
            issues += 1
        flag = "!" if bad else "="
        out.append(f"| {comp_name} | {kind} | {account} | {root_type}/{account_type} | {flag} {reason} |")

    out.append("")
    out.append(f"## Summary: {issues} issue(s) flagged")
    out.append("")

    p = Path("/tmp/step6c_audit_component_accounts.md")
    p.write_text("\n".join(out), encoding="utf-8")
    print()
    for line in out:
        print(line)
    print()
    print(f"[OK] {p}")
    if issues:
        print()
        print(">>> Fix flagged components (Salary Component doctype -> Accounts table)")
        print("    BEFORE creating the May Payroll Entry, otherwise GL will mis-post.")


try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
