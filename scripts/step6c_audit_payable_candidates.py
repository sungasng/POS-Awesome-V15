"""
Phase 6 / Step 6c-AUDIT: list candidate Payroll Payable accounts.

Read-only. No writes. Use this to discover which EXISTING ledger account in
the imported CoA should be wired into Company.default_payroll_payable_account.

Outputs:
    - Current Company.default_payroll_payable_account
    - All leaf accounts with account_type=Payable
    - All leaf Liability accounts whose name contains salary/payroll/wage/staff
    - GL entry count for the orphan `Salary Payable - SCL` (if it exists)

After review, tell the agent the canonical name to use; the next script
(step6c_swap_payable.py) will repoint Company default + disable the orphan.

Run:
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/feat/sungas-customizations/scripts/step6c_audit_payable_candidates.py" -o /tmp/s6c_audit.py
    bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/s6c_audit.py').read())"
"""

from __future__ import annotations
from pathlib import Path
import frappe


COMPANY = "SUNGAS COMPANY LIMITED"


def main():
    print("=" * 72)
    print(" Phase 6 / Step 6c-AUDIT -- Payroll Payable Candidates (READ-ONLY)")
    print("=" * 72)

    out: list[str] = []
    current = frappe.db.get_value("Company", COMPANY, "default_payroll_payable_account")
    out.append(f"Current Company.default_payroll_payable_account = `{current}`")
    out.append("")

    # 1. All leaf Payable accounts
    out.append("## 1. All leaf accounts with account_type='Payable'")
    out.append("")
    rows = frappe.db.sql("""
        select name, account_name, parent_account, account_currency, root_type, disabled
        from `tabAccount`
        where company = %s
          and is_group = 0
          and account_type = 'Payable'
        order by name
    """, (COMPANY,), as_dict=True)
    out.append(f"  Found: {len(rows)}")
    for r in rows:
        flag = " [DISABLED]" if r["disabled"] else ""
        marker = " <-- current" if r["name"] == current else ""
        out.append(f"    - {r['name']:<48} parent=`{r['parent_account']}`{flag}{marker}")
    out.append("")

    # 2. Liability leaf accounts named salary/payroll/wage/staff
    out.append("## 2. Liability leaf accounts whose name suggests salary/payroll/wage/staff")
    out.append("")
    rows = frappe.db.sql("""
        select name, account_name, parent_account, account_type, disabled
        from `tabAccount`
        where company = %s
          and is_group = 0
          and root_type = 'Liability'
          and (
                 name like '%%salary%%'
              or name like '%%payroll%%'
              or name like '%%wage%%'
              or name like '%%staff%%'
              or account_name like '%%Salary%%'
              or account_name like '%%Payroll%%'
              or account_name like '%%Wage%%'
              or account_name like '%%Staff%%'
          )
        order by name
    """, (COMPANY,), as_dict=True)
    out.append(f"  Found: {len(rows)}")
    for r in rows:
        flag = " [DISABLED]" if r["disabled"] else ""
        marker = " <-- current" if r["name"] == current else ""
        out.append(f"    - {r['name']:<48} type=`{r['account_type'] or '-'}` "
                   f"parent=`{r['parent_account']}`{flag}{marker}")
    out.append("")

    # 3. Orphan we just auto-created -- check if safe to disable/delete
    orphan = "Salary Payable - SCL"
    out.append(f"## 3. Auto-created orphan check: `{orphan}`")
    out.append("")
    if frappe.db.exists("Account", orphan):
        gl_count = frappe.db.count("GL Entry", {"account": orphan})
        out.append("  Exists: yes")
        out.append(f"  GL Entries posted: {gl_count}")
        if gl_count == 0:
            out.append("  -> Safe to delete or disable (no transactions yet).")
        else:
            out.append("  -> Cannot delete; contains GL entries. Disable + reroute Company default.")
    else:
        out.append("  Does not exist.")
    out.append("")

    # 4. Top-level Liability groups (so user can spot a missed candidate)
    out.append("## 4. Top-level Liability groups (for context)")
    out.append("")
    rows = frappe.db.sql("""
        select name, account_name, parent_account
        from `tabAccount`
        where company = %s
          and is_group = 1
          and root_type = 'Liability'
        order by name
    """, (COMPANY,), as_dict=True)
    for r in rows:
        out.append(f"    - {r['name']}  (parent=`{r['parent_account'] or '-'}`)")
    out.append("")

    p = Path("/tmp/step6c_audit_payable.md")
    p.write_text("\n".join(out), encoding="utf-8")
    print()
    for line in out:
        print(line)
    print()
    print(f"[OK] {p}")
    print()
    print("NEXT: tell the agent which account name to use as default_payroll_payable_account.")
    print("      The agent will ship step6c_swap_payable.py to repoint Company + disable orphan.")


try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
