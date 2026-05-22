"""
Phase 6 / Step 8b-DIAGNOSE: emulate ERPNext v15 Payroll Entry employee filter.

Walks through each filter ERPNext applies in `get_emp_list()` and reports how
many rows survive each one. Lets us pinpoint which condition is eliminating
all 216 candidates.

Read-only.

Run:
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/feat/sungas-customizations/scripts/step8b_diagnose.py" -o /tmp/s8b_diag.py
    bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/s8b_diag.py').read())"
"""

from __future__ import annotations
import frappe


COMPANY                  = "SUNGAS COMPANY LIMITED"
CURRENCY                 = "NGN"
PAYROLL_FREQUENCY        = "Monthly"
PAYROLL_PAYABLE_ACCOUNT  = "6207 - Salary Control Account - SCL"
PERIOD_START             = "2026-05-01"
PERIOD_END               = "2026-05-31"


def step(title: str, query: str, args: tuple) -> int:
    rows = frappe.db.sql(query, args)
    n = rows[0][0]
    print(f"  {n:>4}  {title}")
    return n


def main():
    print("=" * 72)
    print(f" Phase 6 / Step 8b-DIAGNOSE -- Filter funnel ({PERIOD_START} -> {PERIOD_END})")
    print("=" * 72)
    print()
    print("  Count Filter")
    print("  ----- " + "-" * 60)

    step("All submitted SSAs",
         """select count(*) from `tabSalary Structure Assignment` where docstatus=1""", ())

    step("  + company = SCL",
         """select count(*) from `tabSalary Structure Assignment`
            where docstatus=1 and company=%s""", (COMPANY,))

    step("  + from_date <= end_date",
         """select count(*) from `tabSalary Structure Assignment`
            where docstatus=1 and company=%s and from_date<=%s""",
         (COMPANY, PERIOD_END))

    step("  + payroll_payable_account matches",
         """select count(*) from `tabSalary Structure Assignment`
            where docstatus=1 and company=%s and from_date<=%s
              and payroll_payable_account=%s""",
         (COMPANY, PERIOD_END, PAYROLL_PAYABLE_ACCOUNT))

    step("  + JOIN Salary Structure (active=Yes, NGN, Monthly)",
         """select count(*)
            from `tabSalary Structure Assignment` ssa
            join `tabSalary Structure` ss on ss.name=ssa.salary_structure
            where ssa.docstatus=1 and ssa.company=%s and ssa.from_date<=%s
              and ssa.payroll_payable_account=%s
              and ss.is_active='Yes' and ss.currency=%s and ss.payroll_frequency=%s""",
         (COMPANY, PERIOD_END, PAYROLL_PAYABLE_ACCOUNT, CURRENCY, PAYROLL_FREQUENCY))

    step("  + JOIN Employee (status=Active)",
         """select count(*)
            from `tabSalary Structure Assignment` ssa
            join `tabSalary Structure` ss on ss.name=ssa.salary_structure
            join tabEmployee e on e.name=ssa.employee
            where ssa.docstatus=1 and ssa.company=%s and ssa.from_date<=%s
              and ssa.payroll_payable_account=%s
              and ss.is_active='Yes' and ss.currency=%s and ss.payroll_frequency=%s
              and e.status='Active'""",
         (COMPANY, PERIOD_END, PAYROLL_PAYABLE_ACCOUNT, CURRENCY, PAYROLL_FREQUENCY))

    step("  + Employee.company = SCL",
         """select count(*)
            from `tabSalary Structure Assignment` ssa
            join `tabSalary Structure` ss on ss.name=ssa.salary_structure
            join tabEmployee e on e.name=ssa.employee
            where ssa.docstatus=1 and ssa.company=%s and ssa.from_date<=%s
              and ssa.payroll_payable_account=%s
              and ss.is_active='Yes' and ss.currency=%s and ss.payroll_frequency=%s
              and e.status='Active' and e.company=%s""",
         (COMPANY, PERIOD_END, PAYROLL_PAYABLE_ACCOUNT, CURRENCY, PAYROLL_FREQUENCY, COMPANY))

    step("  + relieving_date IS NULL OR >= start_date",
         """select count(*)
            from `tabSalary Structure Assignment` ssa
            join `tabSalary Structure` ss on ss.name=ssa.salary_structure
            join tabEmployee e on e.name=ssa.employee
            where ssa.docstatus=1 and ssa.company=%s and ssa.from_date<=%s
              and ssa.payroll_payable_account=%s
              and ss.is_active='Yes' and ss.currency=%s and ss.payroll_frequency=%s
              and e.status='Active' and e.company=%s
              and (e.relieving_date is null or e.relieving_date>=%s)""",
         (COMPANY, PERIOD_END, PAYROLL_PAYABLE_ACCOUNT, CURRENCY, PAYROLL_FREQUENCY, COMPANY, PERIOD_START))

    print()
    print("  ----- " + "-" * 60)
    print("  Now: distinct Employee.company values across SSAs (in case of casing drift)")
    rows = frappe.db.sql("""
        select e.company, count(*) as cnt
        from `tabSalary Structure Assignment` ssa
        join tabEmployee e on e.name=ssa.employee
        where ssa.docstatus=1
        group by e.company
    """, as_dict=True)
    for r in rows:
        flag = "  <-- expected" if r["company"] == COMPANY else "  ! MISMATCH"
        print(f"    - {r['company']!r:<40} {r['cnt']:>4}{flag}")

    print()
    print("  Salary Structure inspection")
    ss_rows = frappe.db.sql("""
        select name, is_active, currency, payroll_frequency, company
        from `tabSalary Structure`
        where name in (select distinct salary_structure from `tabSalary Structure Assignment` where docstatus=1)
    """, as_dict=True)
    for s in ss_rows:
        print(f"    - {s['name']!r:<28} company={s['company']!r:<28} "
              f"active={s['is_active']} currency={s['currency']} freq={s['payroll_frequency']}")

    print()
    print("  Sample of NULL/empty payroll_payable_account SSAs (post-fix sanity)")
    rows = frappe.db.sql("""
        select name, employee, payroll_payable_account
        from `tabSalary Structure Assignment`
        where docstatus=1
          and (payroll_payable_account is null or payroll_payable_account='')
        limit 5
    """, as_dict=True)
    if rows:
        for r in rows:
            print(f"    ! {r['name']} -- emp={r['employee']} ppa={r['payroll_payable_account']!r}")
    else:
        print("    = all SSAs have payroll_payable_account set")


try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
