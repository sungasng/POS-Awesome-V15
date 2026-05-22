"""
Phase 6 / Step 8b-FIX: bulk-set Salary Structure Assignment payroll_payable_account.

ERPNext v15's `Payroll Entry.fill_employee_details()` requires that every SSA
have `payroll_payable_account` matching the Payroll Entry's. Our 216 SSAs were
submitted before the Company default was wired, leaving the column NULL --
which makes the May 2026 Payroll Entry pick up 0 employees.

This script bulk-sets `payroll_payable_account = '6207 - Salary Control Account - SCL'`
on every SSA where the field is empty/null. It uses `frappe.db.set_value` so
docstatus=1 SSAs are updated in-place (no resubmit needed).

Side actions:
  1. Cancel + delete the empty Payroll Entry HR-PRUN-2026-00001 (0 slips, safe).
  2. Verify Salary Structure currency + payroll_frequency match company.

DRY_RUN=True   -> print plan, no writes.
DRY_RUN=False  -> commit changes.

Run:
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/feat/sungas-customizations/scripts/step8b_fix_ssa_payable.py" -o /tmp/s8b_fix.py
    bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/s8b_fix.py').read())"
"""

from __future__ import annotations
from pathlib import Path
import frappe


DRY_RUN = True

COMPANY                  = "SUNGAS COMPANY LIMITED"
PAYROLL_PAYABLE_ACCOUNT  = "6207 - Salary Control Account - SCL"
EMPTY_PAYROLL_ENTRY      = "HR-PRUN-2026-00001"   # delete the empty PE we created


def main():
    print("=" * 72)
    print(f" Phase 6 / Step 8b-FIX -- SSA payroll_payable_account (DRY_RUN={DRY_RUN})")
    print("=" * 72)

    out: list[str] = []
    out.append(f"# Step 8b-FIX -- SSA payroll_payable_account (DRY_RUN={DRY_RUN})")
    out.append("")

    # 0. Schema check
    has_field = frappe.get_meta("Salary Structure Assignment").has_field("payroll_payable_account")
    if not has_field:
        print("  ! SSA has no `payroll_payable_account` field on this site -- nothing to do.")
        return

    # 1. Inspect current state
    rows = frappe.db.sql("""
        select name, employee, docstatus, payroll_payable_account, salary_structure
        from `tabSalary Structure Assignment`
        where docstatus = 1
          and (payroll_payable_account is null or payroll_payable_account = '')
        order by name
    """, as_dict=True)
    out.append("## 1. SSAs needing payroll_payable_account update")
    out.append("")
    out.append(f"  Found: {len(rows)}")
    out.append("")
    if rows[:5]:
        out.append("  Sample (first 5):")
        for r in rows[:5]:
            out.append(f"    - {r['name']:<22} emp={r['employee']:<14} struct={r['salary_structure']}")
        out.append("")

    # 2. Salary Structure sanity (currency + payroll_frequency)
    out.append("## 2. Salary Structure sanity")
    out.append("")
    structs = frappe.db.sql("""
        select name, is_active, currency, payroll_frequency, company
        from `tabSalary Structure`
        where name in (select distinct salary_structure from `tabSalary Structure Assignment` where docstatus=1)
    """, as_dict=True)
    for s in structs:
        flag = "OK"
        notes = []
        if s["is_active"] != "Yes":
            notes.append(f"is_active={s['is_active']!r}")
        if (s["currency"] or "NGN") != "NGN":
            notes.append(f"currency={s['currency']!r}")
        if s["payroll_frequency"] != "Monthly":
            notes.append(f"payroll_frequency={s['payroll_frequency']!r}")
        if notes:
            flag = "! " + ", ".join(notes)
        out.append(f"  - `{s['name']}` -> {flag}")
    out.append("")

    # 3. Apply
    out.append("## 3. Update")
    out.append("")
    if not rows:
        out.append("  = nothing to update")
    elif DRY_RUN:
        out.append(f"  + would-set payroll_payable_account = `{PAYROLL_PAYABLE_ACCOUNT}` on {len(rows)} SSAs")
    else:
        for r in rows:
            frappe.db.set_value(
                "Salary Structure Assignment", r["name"],
                "payroll_payable_account", PAYROLL_PAYABLE_ACCOUNT,
                update_modified=False,
            )
        out.append(f"  + updated {len(rows)} SSAs")
    out.append("")

    # 4. Clean up the empty Payroll Entry so we can recreate fresh
    out.append("## 4. Clean up empty Payroll Entry")
    out.append("")
    if frappe.db.exists("Payroll Entry", EMPTY_PAYROLL_ENTRY):
        slip_count = frappe.db.count("Salary Slip", {"payroll_entry": EMPTY_PAYROLL_ENTRY})
        ds = frappe.db.get_value("Payroll Entry", EMPTY_PAYROLL_ENTRY, "docstatus")
        out.append(f"  Found `{EMPTY_PAYROLL_ENTRY}` (docstatus={ds}, child slips={slip_count})")
        if slip_count > 0:
            out.append("  ! HAS SLIPS -- skipping delete; cancel the slips first.")
        elif DRY_RUN:
            out.append(f"  + would-delete `{EMPTY_PAYROLL_ENTRY}`")
        else:
            try:
                if ds == 1:
                    pe = frappe.get_doc("Payroll Entry", EMPTY_PAYROLL_ENTRY)
                    pe.cancel()
                frappe.delete_doc("Payroll Entry", EMPTY_PAYROLL_ENTRY,
                                  ignore_permissions=True, force=1)
                out.append(f"  + deleted `{EMPTY_PAYROLL_ENTRY}`")
            except Exception as e:
                out.append(f"  ! delete failed: {e}")
    else:
        out.append(f"  = `{EMPTY_PAYROLL_ENTRY}` does not exist (already cleaned)")
    out.append("")

    if not DRY_RUN:
        frappe.db.commit()

    p = Path("/tmp/step8b_fix_ssa_payable.md")
    p.write_text("\n".join(out), encoding="utf-8")
    print()
    for line in out:
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
