"""
Phase 6 / Step 8b: Parallel Payroll Run -- CREATE PAYROLL ENTRY.

Inserts a Payroll Entry, fills employee details (Frappe's standard fan-out),
and (optionally) creates Salary Slips in DRAFT for HR review. Does NOT submit
slips or post journals -- that happens after reconciliation in Step 8d (manual)
via the Workflow built in Step 5.

DRY_RUN=True   -> print the projected slip rows; no document is touched.
DRY_RUN=False  -> actually insert the Payroll Entry + Salary Slips.

Inputs (edit before running):
    PERIOD_START, PERIOD_END, PAYMENT_DATE, COMPANY, PAYROLL_FREQUENCY
    POSTING_DATE, EXCHANGE_RATE (default 1)
    CREATE_SLIPS (default True) -- whether to also create slips after the PE

Outputs:
    /tmp/step8b_payroll_create.md         -- summary report
    /tmp/step8b_payroll_create.csv        -- per-employee slip rows
    Payroll Entry name printed at end (use it in step8c + step6b)

Run:
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/feat/sungas-customizations/scripts/step8b_payroll_create.py" -o /tmp/s8b.py
    bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/s8b.py').read())"
"""

from __future__ import annotations
import csv
from pathlib import Path
import frappe


# --- Edit these before running -------------------------------------------------
DRY_RUN = True

PERIOD_START      = "2026-06-01"
PERIOD_END        = "2026-06-30"
POSTING_DATE      = "2026-06-25"
PAYMENT_DATE      = "2026-06-25"
COMPANY           = "Sungas Company Limited"
PAYROLL_FREQUENCY = "Monthly"
EXCHANGE_RATE     = 1.0
CREATE_SLIPS      = True
SUBMIT_PE         = False   # keep PE in Draft so workflow (Step 5) can route it
# -----------------------------------------------------------------------------


def find_existing(report: list[str]) -> str | None:
    """If a PE already exists for this period, surface it -- avoid duplicates."""
    rows = frappe.get_all(
        "Payroll Entry",
        filters={
            "company": COMPANY,
            "start_date": PERIOD_START,
            "end_date": PERIOD_END,
        },
        fields=["name", "docstatus", "creation"],
    )
    if rows:
        names = ", ".join(r["name"] for r in rows)
        report.append(f"  ! Existing Payroll Entry for this period: {names}")
        report.append("    Action: cancel/delete it OR re-use, then re-run.")
        return rows[0]["name"]
    return None


def build_payroll_entry_doc() -> frappe.model.document.Document:
    pe = frappe.new_doc("Payroll Entry")
    pe.company           = COMPANY
    pe.posting_date      = POSTING_DATE
    pe.start_date        = PERIOD_START
    pe.end_date          = PERIOD_END
    pe.payroll_frequency = PAYROLL_FREQUENCY
    pe.payroll_payable_account = frappe.db.get_value(
        "Company", COMPANY, "default_payroll_payable_account"
    ) or frappe.db.get_value(
        "Account",
        {"company": COMPANY, "account_name": "Payroll Payable"},
        "name",
    )
    pe.currency = frappe.db.get_value("Company", COMPANY, "default_currency") or "NGN"
    pe.exchange_rate = EXCHANGE_RATE
    pe.payment_account = frappe.db.get_value(
        "Account",
        {"company": COMPANY, "account_type": "Bank", "is_group": 0},
        "name",
    )
    return pe


def main():
    print("=" * 72)
    print(f" Phase 6 / Step 8b -- Create Payroll Entry (DRY_RUN={DRY_RUN})")
    print(f" Period: {PERIOD_START} -> {PERIOD_END} | Pay Date: {PAYMENT_DATE}")
    print("=" * 72)

    report: list[str] = []
    report.append(f"# Step 8b -- Payroll Entry Creation ({PERIOD_START} -> {PERIOD_END})")
    report.append("")
    report.append(f"_DRY_RUN={DRY_RUN} | Site: {frappe.local.site} | {frappe.utils.now_datetime()}_")
    report.append("")

    if not frappe.db.exists("Company", COMPANY):
        print(f"  ! Company {COMPANY!r} not found")
        return

    existing = find_existing(report)
    if existing and not DRY_RUN:
        print()
        print(f"  Aborting: Payroll Entry for this window already exists ({existing}).")
        print("  Cancel/delete it first, or use it directly in Step 8c/6b.")
        return

    pe = build_payroll_entry_doc()
    report.append("## 1. Payroll Entry Header")
    report.append("")
    report.append(f"  Company             : {pe.company}")
    report.append(f"  Posting Date        : {pe.posting_date}")
    report.append(f"  Period              : {pe.start_date} -> {pe.end_date}")
    report.append(f"  Frequency           : {pe.payroll_frequency}")
    report.append(f"  Currency            : {pe.currency}")
    report.append(f"  Payroll Payable A/c : {pe.payroll_payable_account}")
    report.append(f"  Payment A/c         : {pe.payment_account}")
    report.append("")

    if not pe.payroll_payable_account:
        report.append("  ! Missing payroll_payable_account on Company. Set it before LIVE run.")
    if not pe.payment_account:
        report.append("  ! Could not auto-resolve a Bank Account on this Company.")

    # Resolve the universe of employees the PE would pick up.
    # (This mirrors Frappe's own `fill_employee_details` filter.)
    emp_rows = frappe.db.sql("""
        select e.name as employee,
               e.employee_name,
               e.department,
               e.branch,
               e.designation,
               e.payroll_cost_center,
               ssa.salary_structure,
               ssa.base
        from `tabSalary Structure Assignment` ssa
        join tabEmployee e on e.name = ssa.employee
        where ssa.docstatus = 1
          and e.status = 'Active'
          and ssa.from_date <= %s
          and (e.relieving_date is null or e.relieving_date >= %s)
          and (e.date_of_joining is null or e.date_of_joining <= %s)
        order by e.employee_name
    """, (PERIOD_END, PERIOD_START, PERIOD_END), as_dict=True)

    # Keep latest SSA per employee (results were ordered by date desc within step8a; here just dedupe)
    seen, dedup = set(), []
    for r in emp_rows:
        if r["employee"] in seen:
            continue
        seen.add(r["employee"])
        dedup.append(r)

    report.append(f"## 2. Employees in window: {len(dedup)}")
    report.append("")
    csv_path = Path("/tmp/step8b_payroll_create.csv")
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(dedup[0].keys()) if dedup else
                                       ["employee", "employee_name", "salary_structure", "base"])
        w.writeheader()
        for r in dedup:
            w.writerow(r)

    if DRY_RUN:
        print()
        for line in report:
            print(line)
        print()
        print(f"[DRY_RUN] Wrote roster: {csv_path} ({len(dedup)} rows)")
        print("[DRY_RUN] No documents were inserted. Set DRY_RUN=False to create the Payroll Entry.")
        Path("/tmp/step8b_payroll_create.md").write_text("\n".join(report), encoding="utf-8")
        return

    # ---------- LIVE: insert PE ----------
    pe.insert(ignore_permissions=True)
    frappe.db.commit()
    report.append(f"  + Payroll Entry created: `{pe.name}`")
    print(f"  + Payroll Entry created: {pe.name}")

    # Fill employee table using ERPNext's own helper (handles filters + dedup + branch checks).
    try:
        pe.fill_employee_details()
        pe.save(ignore_permissions=True)
        frappe.db.commit()
        report.append(f"  + fill_employee_details(): {len(pe.employees)} employees attached")
        print(f"  + fill_employee_details(): {len(pe.employees)} employees attached")
    except Exception as e:
        report.append(f"  ! fill_employee_details() failed: {e}")
        print(f"  ! fill_employee_details() failed: {e}")

    # Create Salary Slips in draft
    if CREATE_SLIPS:
        try:
            res = pe.create_salary_slips()
            frappe.db.commit()
            report.append(f"  + create_salary_slips(): triggered (return={res!r})")
            slip_count = frappe.db.count("Salary Slip", {"payroll_entry": pe.name})
            report.append(f"    Salary Slips now in draft: {slip_count}")
            print(f"  + Salary Slips in draft: {slip_count}")
        except Exception as e:
            report.append(f"  ! create_salary_slips() failed: {e}")
            print(f"  ! create_salary_slips() failed: {e}")

    if SUBMIT_PE:
        try:
            pe.submit()
            frappe.db.commit()
            report.append("  + Payroll Entry submitted")
        except Exception as e:
            report.append(f"  ! submit() failed -- leave for workflow review: {e}")

    Path("/tmp/step8b_payroll_create.md").write_text("\n".join(report), encoding="utf-8")
    print()
    for line in report:
        print(line)
    print()
    print(f"Payroll Entry: {pe.name}")
    print("Next: run step8c with PAYROLL_ENTRY=" + pe.name + " and your Excel baseline CSV at /tmp/payroll_excel_baseline.csv")


try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
