"""
Phase 6 / Step 8b -- Diagnose why slips end up with 0 earnings.

After fix #2 (submit Sungas Standard), step8b inserted all 216 slips,
but they all have gross_pay=0 / net_pay=0 and EMPTY earnings + deductions
tables. This script answers:

  1. Does Salary Structure 'Sungas Standard' actually HAVE earnings rows?
     If yes, list them (component, abbr, formula, condition, statistical,
     do_not_include_in_total).
  2. Same for deductions.
  3. Pick one slip (HR-EMP-00057), dump its Salary Detail children
     (earnings + deductions tables in DB).
  4. Compute what get_emp_and_working_day_details() would do for that
     employee by manually running pull_sal_struct (via make_salary_slip).
  5. If the structure rows exist but slips are empty -> the slip-create
     path didn't run validate() properly OR `make_salary_slip` failed
     silently. Repopulate one slip in-place and report.

Read-only by default (REPOPULATE=False). Set REPOPULATE=True to run a
one-employee fix attempt on slip Sal Slip/HR-EMP-00057/00004.
"""

from __future__ import annotations
import frappe


REPOPULATE      = False
PROBE_EMPLOYEE  = "HR-EMP-00057"
STRUCTURE_NAME  = "Sungas Standard"


def main() -> None:
    print("=" * 72)
    print(" Diagnose: empty earnings/deductions on May 2026 slips")
    print("=" * 72)
    print()

    # ---- 1+2. Structure rows ----
    print(f"## Salary Structure '{STRUCTURE_NAME}' rows")
    print()
    for ctype in ("earnings", "deductions"):
        rows = frappe.db.sql("""
            select salary_component, abbr, amount_based_on_formula, formula,
                   amount, `condition`, statistical_component, do_not_include_in_total, idx
            from `tabSalary Detail`
            where parent = %s and parentfield = %s
            order by idx
        """, (STRUCTURE_NAME, ctype), as_dict=True)
        print(f"  {ctype.upper():<10}  ({len(rows)} rows)")
        for r in rows:
            stat = " STAT" if r.get("statistical_component") else ""
            print(f"    {r['idx']:<3} {r['salary_component']!s:<24} "
                  f"abbr={r['abbr']!s:<6} formula?={r.get('amount_based_on_formula')}"
                  f"  amount={r['amount']}{stat}")
            if r.get("condition"):
                print(f"        condition: {r['condition']!r}")
            if r.get("formula"):
                print(f"        formula  : {r['formula']!r}")
        print()

    # ---- 3. Probe one slip ----
    slip_name = frappe.db.get_value(
        "Salary Slip",
        {"employee": PROBE_EMPLOYEE, "payroll_entry": "HR-PRUN-2026-00001"},
        "name",
    )
    print(f"## Slip for {PROBE_EMPLOYEE}: {slip_name}")
    print()
    if not slip_name:
        print("  ! Slip not found")
        return

    slip_meta = frappe.db.get_value(
        "Salary Slip", slip_name,
        ["docstatus", "salary_structure", "base", "gross_pay", "net_pay",
         "total_working_days", "payment_days"], as_dict=True,
    )
    print(f"  {slip_meta}")
    print()

    for ctype in ("earnings", "deductions"):
        rows = frappe.db.sql("""
            select salary_component, abbr, amount, default_amount,
                   do_not_include_in_total, statistical_component
            from `tabSalary Detail`
            where parent = %s and parentfield = %s
            order by idx
        """, (slip_name, ctype), as_dict=True)
        print(f"  Slip.{ctype}: {len(rows)} rows")
        for r in rows:
            print(f"    - {r}")
        print()

    # ---- 4. Replay pull_sal_struct in-memory ----
    print("## Replay make_salary_slip in memory (no DB write)")
    print()
    try:
        from hrms.payroll.doctype.salary_structure.salary_structure import make_salary_slip
        tmp = make_salary_slip(STRUCTURE_NAME, employee=PROBE_EMPLOYEE)
        tmp.start_date  = "2026-05-01"
        tmp.end_date    = "2026-05-31"
        tmp.posting_date = "2026-05-25"
        tmp.payroll_frequency = "Monthly"
        # process_salary_structure already ran inside make_salary_slip postprocess
        print(f"  tmp.base       = {tmp.base}")
        print(f"  tmp.gross_pay  = {tmp.gross_pay}")
        print(f"  tmp.net_pay    = {tmp.net_pay}")
        print(f"  tmp.earnings   = {len(tmp.earnings or [])} rows")
        for e in (tmp.earnings or [])[:8]:
            print(f"    + {e.salary_component:<24} amount={e.amount}")
        print(f"  tmp.deductions = {len(tmp.deductions or [])} rows")
        for d in (tmp.deductions or [])[:8]:
            print(f"    - {d.salary_component:<24} amount={d.amount}")
    except Exception as e:
        print(f"  ! make_salary_slip failed: {e!r}")
        import traceback
        traceback.print_exc()

    # ---- 5. Repopulate fix ----
    if REPOPULATE and slip_name:
        print()
        print("## REPOPULATE = True -- recompute one slip in-place")
        slip = frappe.get_doc("Salary Slip", slip_name)
        slip.earnings = []
        slip.deductions = []
        try:
            slip.get_emp_and_working_day_details()
            slip.set_salary_structure_assignment()
            slip.calculate_net_pay()
            slip.save(ignore_permissions=True)
            frappe.db.commit()
            print(f"  + Recomputed. gross={slip.gross_pay} net={slip.net_pay} "
                  f"earnings={len(slip.earnings or [])} deductions={len(slip.deductions or [])}")
        except Exception as e:
            print(f"  ! recompute failed: {e!r}")
            import traceback
            traceback.print_exc()


# bench execute scope-fix
try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
