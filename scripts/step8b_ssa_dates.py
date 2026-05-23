"""
Phase 6 / Step 8b -- SSA from_date investigation + auto-repair.

Hypothesis: When the 148 SSAs were cancelled+resubmitted on 2026-05-19 to fix
the 10x bug (PRD step 3a), their `from_date` was set to the resubmit date
(2026-05-19), not 2026-05-01. step3e was supposed to backdate them but may
have skipped already-submitted SSAs.

This causes:
  - step8b's roster query (`from_date <= 2026-05-31`) still finds them.
  - HRMS slip lookup (`from_date <= 2026-05-01`) does NOT find them.
  -> "Please assign a Salary Structure ... applicable from or before 01-05-2026"

This script:
  1. Prints from_date distribution of all submitted SSAs.
  2. If DRY_RUN=False, SQL-UPDATEs every submitted SSA whose from_date is
     between 2026-05-02 and 2026-05-31 back to 2026-05-01.

Run (diagnose only):
    SHA=<sha>
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/$SHA/scripts/step8b_ssa_dates.py" -o /tmp/s8b_dates.py
    bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/s8b_dates.py').read())"

Run (repair):
    sed -i 's/^DRY_RUN = True$/DRY_RUN = False/' /tmp/s8b_dates.py
    bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/s8b_dates.py').read())"
"""

from __future__ import annotations
import frappe


DRY_RUN       = True
TARGET_DATE   = "2026-05-01"
COMPANY       = "SUNGAS COMPANY LIMITED"
WINDOW_START  = "2026-05-02"   # SSAs dated between these will be back-dated
WINDOW_END    = "2026-05-31"


def main() -> None:
    print("=" * 72)
    print(f" Step 8b -- SSA from_date investigation  (DRY_RUN={DRY_RUN})")
    print("=" * 72)

    # ---- 1. Distribution ----
    dist = frappe.db.sql("""
        select ssa.from_date, count(*) as n
        from `tabSalary Structure Assignment` ssa
        join `tabEmployee` e on e.name = ssa.employee
        where ssa.docstatus = 1
          and e.status = 'Active'
          and e.company = %s
        group by ssa.from_date
        order by ssa.from_date
    """, COMPANY, as_dict=True)

    print()
    print("  from_date     count")
    print("  -----------   -----")
    for r in dist:
        marker = "  <-- AFTER 2026-05-01" if str(r["from_date"]) > TARGET_DATE else ""
        print(f"  {r['from_date']}    {r['n']:>4}{marker}")
    print()

    # ---- 2. Candidates to backdate ----
    candidates = frappe.db.sql("""
        select ssa.name, ssa.employee, ssa.from_date, ssa.salary_structure
        from `tabSalary Structure Assignment` ssa
        join `tabEmployee` e on e.name = ssa.employee
        where ssa.docstatus = 1
          and e.status = 'Active'
          and e.company = %s
          and ssa.from_date between %s and %s
        order by ssa.from_date, ssa.employee
    """, (COMPANY, WINDOW_START, WINDOW_END), as_dict=True)

    print(f"  Submitted SSAs with from_date in {WINDOW_START}..{WINDOW_END}: {len(candidates)}")
    if candidates[:10]:
        print("  Sample (first 10):")
        for r in candidates[:10]:
            print(f"    - {r['name']}  emp={r['employee']}  from_date={r['from_date']}")
    print()

    if not candidates:
        print("  Nothing to do -- no SSAs in repair window.")
        return

    if DRY_RUN:
        print("  [DRY_RUN] No changes made. Set DRY_RUN=False to back-date.")
        return

    # ---- 3. Repair (raw SQL -- submitted docs, bypass validation) ----
    frappe.db.sql("""
        update `tabSalary Structure Assignment` ssa
        join `tabEmployee` e on e.name = ssa.employee
        set ssa.from_date = %s, ssa.modified = NOW()
        where ssa.docstatus = 1
          and e.status = 'Active'
          and e.company = %s
          and ssa.from_date between %s and %s
    """, (TARGET_DATE, COMPANY, WINDOW_START, WINDOW_END))
    frappe.db.commit()

    n = len(candidates)
    print(f"  + Repaired {n} SSAs -- from_date set to {TARGET_DATE}")

    # ---- 4. Verify ----
    still_bad = frappe.db.sql("""
        select count(*)
        from `tabSalary Structure Assignment` ssa
        join `tabEmployee` e on e.name = ssa.employee
        where ssa.docstatus = 1
          and e.status = 'Active'
          and e.company = %s
          and ssa.from_date > %s
    """, (COMPANY, TARGET_DATE))[0][0]
    print(f"  Remaining SSAs with from_date > {TARGET_DATE}: {still_bad}")


# bench-execute scope-fix
try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
