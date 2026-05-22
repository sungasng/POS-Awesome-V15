"""
Phase 6 / Step 3e: Back-date Salary Structure Assignments.

Phase 6 / Step 2c.3 submitted 217+ SSAs with from_date = 2026-06-01. To run a
parallel May 2026 payroll, those SSAs must be effective on or before
2026-05-01. This script shifts every active submitted SSA whose from_date is
later than NEW_FROM_DATE down to NEW_FROM_DATE.

Idempotent: SSAs already effective at/before the target are skipped. Submitted
SSAs are mutated via `frappe.db.set_value` (direct DB write, bypasses workflow
validators) -- safe because no Salary Slip has been posted for the new period
yet (verified at top of script).

DRY_RUN=True   -> list the SSAs that would shift.
DRY_RUN=False  -> persist the from_date change + commit.

Run:
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/feat/sungas-customizations/scripts/step3e_backdate_ssas.py" -o /tmp/s3e.py
    bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/s3e.py').read())"
"""

from __future__ import annotations
from pathlib import Path
import frappe


DRY_RUN = True
NEW_FROM_DATE = "2026-05-01"


def main():
    print("=" * 72)
    print(f" Phase 6 / Step 3e -- Back-date SSAs to {NEW_FROM_DATE} (DRY_RUN={DRY_RUN})")
    print("=" * 72)

    # Safety: refuse to shift if any submitted Salary Slip exists in the affected window.
    risky_slips = frappe.db.sql("""
        select count(*)
        from `tabSalary Slip`
        where docstatus = 1
          and start_date >= %s
    """, (NEW_FROM_DATE,))[0][0]
    if risky_slips:
        print(f"  ! Aborting: {risky_slips} submitted Salary Slip(s) already exist on/after {NEW_FROM_DATE}")
        print("    Cancel those slips first, then re-run.")
        return

    rows = frappe.db.sql("""
        select name, employee, salary_structure, from_date, base, docstatus
        from `tabSalary Structure Assignment`
        where docstatus = 1
          and from_date > %s
        order by employee, from_date
    """, (NEW_FROM_DATE,), as_dict=True)

    print(f"  SSAs to back-date: {len(rows)}")
    if not rows:
        print("  Nothing to do.")
        return

    if rows[:10]:
        print()
        print("  Preview (first 10):")
        for r in rows[:10]:
            print(f"    - {r['name']:<22} {r['employee']:>14}  "
                  f"{r['from_date']} -> {NEW_FROM_DATE}  base={float(r['base'] or 0):>12,.2f}")

    if DRY_RUN:
        print()
        print("[DRY_RUN] No changes written. Set DRY_RUN=False to apply.")
    else:
        for r in rows:
            frappe.db.set_value(
                "Salary Structure Assignment", r["name"],
                "from_date", NEW_FROM_DATE,
                update_modified=False,
            )
        frappe.db.commit()
        print()
        print(f"[OK] Updated from_date on {len(rows)} SSAs.")

    # Markdown report
    md = [
        f"# Step 3e -- SSA Back-date Report (DRY_RUN={DRY_RUN})",
        "",
        f"_Generated: {frappe.utils.now_datetime()} | Site: {frappe.local.site}_",
        "",
        f"- Target from_date : {NEW_FROM_DATE}",
        f"- Rows affected    : {len(rows)}",
        "",
        "## Affected SSAs",
        "",
        "| SSA | Employee | Old from_date | New from_date | Base |",
        "|-----|----------|--------------:|--------------:|-----:|",
    ]
    for r in rows:
        md.append(f"| {r['name']} | {r['employee']} | {r['from_date']} | "
                  f"{NEW_FROM_DATE} | {float(r['base'] or 0):,.2f} |")
    p = Path("/tmp/step3e_backdate_ssas.md")
    p.write_text("\n".join(md), encoding="utf-8")
    print(f"\n[OK] {p}")


try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
