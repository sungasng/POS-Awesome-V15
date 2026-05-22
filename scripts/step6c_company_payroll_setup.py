"""
Phase 6 / Step 6c: Company-level Payroll wiring.

Wires the two Company-level fields that the Payroll Entry doctype requires:

  1. default_payroll_payable_account -- the GL account where Net Pay is
     credited until disbursement. Looks up an existing "Salary Payable" or
     "Payroll Payable" account, otherwise creates a new ledger account
     under "Accounts Payable" with `account_type=Payable`.

  2. default_holiday_list -- needed for attendance / leave balance calc.
     Defaults to the HQ list (most employees follow it; outlet employees
     have their own list overridden per-Employee in Step 4a).

Idempotent. Set DRY_RUN=True to preview.

Run:
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/feat/sungas-customizations/scripts/step6c_company_payroll_setup.py" -o /tmp/s6c.py
    bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/s6c.py').read())"
"""

from __future__ import annotations
from pathlib import Path
import frappe


DRY_RUN = True

COMPANY                  = "SUNGAS COMPANY LIMITED"
DEFAULT_HOLIDAY_LIST     = "Sungas HQ Holidays 2026"
PAYROLL_PAYABLE_NAME     = "Salary Payable"   # account_name to seek/create


def find_existing_payable() -> str | None:
    """Search the imported CoA for an existing Payroll Payable account.

    Tries account_name match first across common synonyms, then falls back
    to fuzzy LIKE on every Liability leaf account whose name suggests
    salary/payroll. Returns the first single non-disabled match, or None.
    """
    candidates = ["Salary Payable", "Payroll Payable", "Payable Salary",
                  "Salary Control Account", "Salaries Payable"]
    for c in candidates:
        n = frappe.db.get_value(
            "Account",
            {"company": COMPANY, "account_name": c, "is_group": 0, "disabled": 0},
            "name",
        )
        if n:
            return n
    # Fuzzy search across any Liability leaf
    rows = frappe.db.sql("""
        select name
        from `tabAccount`
        where company = %s
          and is_group = 0
          and disabled = 0
          and root_type = 'Liability'
          and (
                 name like '%%Salary%%'
              or name like '%%Payroll%%'
              or account_name like '%%Salary%%'
              or account_name like '%%Payroll%%'
          )
        order by name
        limit 1
    """, (COMPANY,), as_dict=True)
    if rows:
        return rows[0]["name"]
    return None


def main():
    print("=" * 72)
    print(f" Phase 6 / Step 6c -- Company Payroll Setup (DRY_RUN={DRY_RUN})")
    print("=" * 72)

    report: list[str] = []
    report.append(f"# Step 6c -- Company Payroll Setup (DRY_RUN={DRY_RUN})")
    report.append("")
    report.append(f"_Generated: {frappe.utils.now_datetime()} | Site: {frappe.local.site}_")
    report.append("")

    company = frappe.db.get_value(
        "Company", COMPANY,
        ["name", "default_holiday_list", "default_payroll_payable_account", "abbr"],
        as_dict=True,
    )
    if not company:
        print(f"  ! Company {COMPANY!r} not found")
        return

    report.append(f"  Company: `{company['name']}` (abbr={company.get('abbr')!r})")
    report.append("")

    # ---- Holiday list ----
    report.append("## 1. Default Holiday List")
    report.append("")
    if company.get("default_holiday_list"):
        report.append(f"  = already set: `{company['default_holiday_list']}`")
    elif not frappe.db.exists("Holiday List", DEFAULT_HOLIDAY_LIST):
        report.append(f"  ! Target list `{DEFAULT_HOLIDAY_LIST}` does not exist on ERP")
    else:
        if DRY_RUN:
            report.append(f"  + would-set Company.default_holiday_list = `{DEFAULT_HOLIDAY_LIST}`")
        else:
            frappe.db.set_value("Company", COMPANY, "default_holiday_list", DEFAULT_HOLIDAY_LIST)
            report.append(f"  + Company.default_holiday_list = `{DEFAULT_HOLIDAY_LIST}`")
    report.append("")

    # ---- Payroll Payable account ----
    report.append("## 2. Default Payroll Payable Account")
    report.append("")
    if company.get("default_payroll_payable_account"):
        report.append(f"  = already set: `{company['default_payroll_payable_account']}`")
    else:
        acct = find_existing_payable()
        if acct:
            report.append(f"  = found existing payable account: `{acct}`")
            if DRY_RUN:
                report.append(f"  + would-set Company.default_payroll_payable_account = `{acct}`")
            else:
                frappe.db.set_value("Company", COMPANY, "default_payroll_payable_account", acct)
                report.append(f"  + Company.default_payroll_payable_account = `{acct}`")
        else:
            report.append("  ! NO existing payable account named Salary/Payroll/Wage found.")
            report.append("    Run `step6c_audit_payable_candidates.py` to list candidates,")
            report.append("    then `step6c_swap_payable.py` to wire the canonical CoA account.")
            report.append("    (This script will NOT auto-create new GL accounts.)")
    report.append("")

    if not DRY_RUN:
        frappe.db.commit()

    p = Path("/tmp/step6c_company_payroll_setup.md")
    p.write_text("\n".join(report), encoding="utf-8")
    print()
    for line in report:
        print(line)
    print()
    print(f"[OK] {p}")
    if DRY_RUN:
        print()
        print("[DRY_RUN] No changes written. Set DRY_RUN=False and re-run to apply.")


try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
