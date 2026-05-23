"""
Phase 6 / Step 8b -- Deeper probe: structure row formulas + component master + one slip.

Same as step8b_diagnose_empty.py but:
  - Prints formula/condition columns UNCONDITIONALLY (no truthy gate).
  - Also dumps Salary Component master to see if formulas live there.
  - Removes invalid `base` column from Salary Slip probe (base lives on SSA).
  - Reads slip earnings/deductions directly from `tabSalary Detail`.
"""

from __future__ import annotations
import frappe


STRUCTURE_NAME = "Sungas Standard"
PROBE_EMPLOYEE = "HR-EMP-00057"


def main() -> None:
    print("=" * 72)
    print(" Deep probe -- structure rows + component master + slip child rows")
    print("=" * 72)
    print()

    # ---- 1. Structure rows -- print formula/condition raw (no truthy gate) ----
    for ctype in ("earnings", "deductions"):
        rows = frappe.db.sql("""
            select idx, salary_component, abbr, amount_based_on_formula, formula,
                   amount, `condition`, statistical_component, do_not_include_in_total
            from `tabSalary Detail`
            where parent = %s and parentfield = %s
            order by idx
        """, (STRUCTURE_NAME, ctype), as_dict=True)
        print(f"## Structure '{STRUCTURE_NAME}' {ctype}: {len(rows)} rows")
        for r in rows:
            print(f"  [{r['idx']}] {r['salary_component']!s:<26} abbr={r['abbr']!s:<8} "
                  f"abf={r['amount_based_on_formula']}  amount={r['amount']}  "
                  f"stat={r['statistical_component']}  do_not_inc={r['do_not_include_in_total']}")
            print(f"       condition = {r['condition']!r}")
            print(f"       formula   = {r['formula']!r}")
        print()

    # ---- 2. Salary Component master ----
    print("## Salary Component master (formula + condition columns)")
    comps = frappe.db.sql("""
        select sc.name, sc.salary_component_abbr, sc.type,
               sc.amount_based_on_formula, sc.formula, sc.`condition`,
               sc.statistical_component, sc.do_not_include_in_total
        from `tabSalary Component` sc
        where sc.name in (
            select distinct salary_component from `tabSalary Detail`
            where parent = %s
        )
        order by sc.type, sc.name
    """, STRUCTURE_NAME, as_dict=True)
    for c in comps:
        print(f"  {c['name']!s:<28} abbr={c['salary_component_abbr']!s:<8} "
              f"type={c['type']!s:<10} abf={c['amount_based_on_formula']}  "
              f"stat={c['statistical_component']}  do_not_inc={c['do_not_include_in_total']}")
        print(f"       condition = {c['condition']!r}")
        print(f"       formula   = {c['formula']!r}")
    print()

    # ---- 3. Slip header (avoid the non-existent `base` column) ----
    slip_name = frappe.db.get_value(
        "Salary Slip",
        {"employee": PROBE_EMPLOYEE, "payroll_entry": "HR-PRUN-2026-00001"},
        "name",
    )
    print(f"## Slip for {PROBE_EMPLOYEE}: {slip_name}")
    if slip_name:
        meta = frappe.db.get_value(
            "Salary Slip", slip_name,
            ["docstatus", "salary_structure", "gross_pay", "net_pay",
             "total_working_days", "payment_days"], as_dict=True,
        )
        print(f"  {meta}")
        for ctype in ("earnings", "deductions"):
            rows = frappe.db.sql("""
                select salary_component, abbr, amount, default_amount,
                       statistical_component, do_not_include_in_total
                from `tabSalary Detail`
                where parent = %s and parentfield = %s
                order by idx
            """, (slip_name, ctype), as_dict=True)
            print(f"  slip.{ctype}: {len(rows)} rows")
            for r in rows:
                print(f"    {r}")
    print()

    # ---- 4. SSA -> see what base value the formula would receive ----
    print("## SSA for probe employee")
    ssa = frappe.db.sql("""
        select name, salary_structure, base, variable, from_date,
               payroll_payable_account, income_tax_slab
        from `tabSalary Structure Assignment`
        where employee = %s and docstatus = 1
        order by from_date desc limit 1
    """, PROBE_EMPLOYEE, as_dict=True)
    print(f"  {ssa[0] if ssa else 'NONE'}")
    print()

    # ---- 5. Try make_salary_slip in memory and report what comes back ----
    print("## Replay make_salary_slip(structure, employee=...) in memory")
    try:
        from hrms.payroll.doctype.salary_structure.salary_structure import make_salary_slip
        tmp = make_salary_slip(STRUCTURE_NAME, employee=PROBE_EMPLOYEE)
        tmp.start_date = "2026-05-01"
        tmp.end_date   = "2026-05-31"
        tmp.posting_date = "2026-05-25"
        tmp.payroll_frequency = "Monthly"
        tmp.process_salary_structure()
        print(f"  tmp.gross_pay = {tmp.gross_pay} | tmp.net_pay = {tmp.net_pay}")
        print(f"  tmp.earnings ({len(tmp.earnings or [])}):")
        for e in (tmp.earnings or []):
            print(f"    + {e.salary_component:<26} amount={e.amount} default={e.default_amount}")
        print(f"  tmp.deductions ({len(tmp.deductions or [])}):")
        for d in (tmp.deductions or []):
            print(f"    - {d.salary_component:<26} amount={d.amount} default={d.default_amount}")
    except Exception as e:
        print(f"  ! make_salary_slip / process_salary_structure failed: {e!r}")
        import traceback
        traceback.print_exc()


try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
