"""
Phase 6 / Step 8b -- SPOT CHECK helper.

After step8b creates the draft Salary Slips, this script pulls a small sample
(default: 4 random slips for the chosen Payroll Entry) and prints earnings +
deductions + Net Pay in a readable table. Use it to eyeball the ERP numbers
against the legacy Excel sheet before running step8c (full reconciliation).

Read-only. Does not insert/update any document.

Inputs (edit before running):
    PAYROLL_ENTRY  -- name of the PE created by step8b (REQUIRED)
    SAMPLE_SIZE    -- how many slips to spot-check (default 4)
    PICK_EMPLOYEES -- optional list of specific employee IDs to include
                     (these are ADDED on top of the random sample)

Run:
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/<commit_sha>/scripts/step8b_spotcheck.py" -o /tmp/s8b_spot.py
    bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/s8b_spot.py').read())"

Output:
    Prints to stdout. Also writes /tmp/step8b_spotcheck.md.
"""

from __future__ import annotations
import random
from pathlib import Path
import frappe


# --- Edit these before running ------------------------------------------------
PAYROLL_ENTRY  = ""          # e.g. "MAT-PE-2026-00001" -- fill in!
SAMPLE_SIZE    = 4
PICK_EMPLOYEES = []          # e.g. ["HR-EMP-00001", "HR-EMP-00050"]
# -----------------------------------------------------------------------------


def fmt_money(v) -> str:
    try:
        return f"{float(v or 0):>16,.2f}"
    except Exception:
        return f"{v!s:>16}"


def render_slip(slip, lines: list[str]) -> None:
    head = f"=== {slip.name} | {slip.employee} {slip.employee_name} | {slip.start_date} -> {slip.end_date} ==="
    lines.append("")
    lines.append(head)
    lines.append(f"  Structure       : {slip.salary_structure}")
    lines.append(f"  Department      : {getattr(slip, 'department', '') or ''}")
    lines.append(f"  Designation     : {getattr(slip, 'designation', '') or ''}")
    lines.append(f"  Branch          : {getattr(slip, 'branch', '') or ''}")
    lines.append(f"  Working Days    : {slip.total_working_days} | Payment Days: {slip.payment_days}")
    lines.append("")
    lines.append("  EARNINGS                                          AMOUNT (NGN)")
    lines.append("  " + "-" * 64)
    for row in (slip.earnings or []):
        flag = "*" if getattr(row, "statistical_component", 0) else " "
        name = f"{flag} {row.salary_component}"
        lines.append(f"  {name:<48}{fmt_money(row.amount)}")
    lines.append("  " + "-" * 64)
    lines.append(f"  {'Gross Pay':<48}{fmt_money(slip.gross_pay)}")
    lines.append("")
    lines.append("  DEDUCTIONS                                        AMOUNT (NGN)")
    lines.append("  " + "-" * 64)
    for row in (slip.deductions or []):
        lines.append(f"   {row.salary_component:<47}{fmt_money(row.amount)}")
    lines.append("  " + "-" * 64)
    lines.append(f"  {'Total Deduction':<48}{fmt_money(slip.total_deduction)}")
    lines.append("")
    lines.append(f"  {'NET PAY':<48}{fmt_money(slip.net_pay)}")
    lines.append("")
    lines.append("  (* = statistical / slip-only component, does not post to GL)")


def main() -> None:
    if not PAYROLL_ENTRY:
        print("ERROR: edit PAYROLL_ENTRY at the top of this script before running.")
        return
    if not frappe.db.exists("Payroll Entry", PAYROLL_ENTRY):
        print(f"ERROR: Payroll Entry '{PAYROLL_ENTRY}' not found.")
        return

    pe = frappe.get_doc("Payroll Entry", PAYROLL_ENTRY)
    print("=" * 72)
    print(f" Spot check  |  PE: {pe.name}  |  {pe.start_date} -> {pe.end_date}")
    print(f" Company: {pe.company}  |  Frequency: {pe.payroll_frequency}")
    print("=" * 72)

    all_slips = frappe.get_all(
        "Salary Slip",
        filters={"payroll_entry": pe.name},
        fields=["name", "employee", "employee_name", "net_pay", "gross_pay"],
        order_by="employee_name asc",
    )
    print(f" Draft slips found: {len(all_slips)}")
    if not all_slips:
        print(" Nothing to spot-check.")
        return

    picked: list[str] = []
    # Explicit picks first
    by_emp = {s["employee"]: s for s in all_slips}
    for emp in PICK_EMPLOYEES:
        if emp in by_emp:
            picked.append(by_emp[emp]["name"])
    # Fill the rest with a random sample (deterministic seed so repeat runs are stable)
    remaining = [s["name"] for s in all_slips if s["name"] not in picked]
    rng = random.Random(42)
    rng.shuffle(remaining)
    while len(picked) < SAMPLE_SIZE and remaining:
        picked.append(remaining.pop())

    lines: list[str] = []
    lines.append(f"# Step 8b -- Spot Check ({pe.name})")
    lines.append("")
    lines.append(f"Period: {pe.start_date} -> {pe.end_date}  |  Slips total: {len(all_slips)}  |  Sampled: {len(picked)}")

    grand_gross = grand_net = 0.0
    for slip_name in picked:
        slip = frappe.get_doc("Salary Slip", slip_name)
        render_slip(slip, lines)
        grand_gross += float(slip.gross_pay or 0)
        grand_net   += float(slip.net_pay or 0)

    lines.append("")
    lines.append(f"Sample totals  Gross: NGN {grand_gross:,.2f}  Net: NGN {grand_net:,.2f}")

    out = "\n".join(lines)
    Path("/tmp/step8b_spotcheck.md").write_text(out, encoding="utf-8")
    print(out)
    print()
    print("[OK] /tmp/step8b_spotcheck.md")


# bench execute scope-fix
try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
