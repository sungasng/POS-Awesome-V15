"""
Phase 6 / Step 8c: Parallel Payroll Run -- RECONCILE ERP vs EXCEL BASELINE.

Compares each ERP Salary Slip (in draft or submitted) against a CSV exported
from the legacy Excel payroll. Produces a per-employee variance report so HR /
Finance can sign off before workflow approval.

Excel baseline CSV (place at /tmp/payroll_excel_baseline.csv) -- columns:

    employee,gross,paye,pension_ee,nhf,nhis,net
    HR-EMP-00001,450000,52340,28000,7500,5250,357010
    HR-EMP-00002,...

Notes:
    - `employee` MUST be the ERP Employee.name (e.g., HR-EMP-00001)
      OR the legacy `attendance_device_id` if you mapped that column.
    - Currency: NGN, no commas, no symbols.

Inputs (edit before running):
    PAYROLL_ENTRY               -- ERP Payroll Entry name
    BASELINE_CSV                -- path to Excel-exported baseline CSV
    VARIANCE_THRESHOLD          -- absolute NGN delta over which a row is flagged

Outputs:
    /tmp/step8c_reconciliation.md      -- summary + variance buckets
    /tmp/step8c_reconciliation.csv     -- full per-employee delta table

Run:
    # 1. Upload Excel baseline -- via your local terminal:
    #    scp payroll_excel_baseline.csv frappecloud:~/frappe-bench/sites/sungasmis.v.frappe.cloud/private/files/
    #    OR drop it under Desk -> File and copy to /tmp before running:
    #    cp ~/frappe-bench/sites/sungasmis.v.frappe.cloud/private/files/payroll_excel_baseline.csv /tmp/
    # 2. Run:
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/feat/sungas-customizations/scripts/step8c_payroll_reconcile.py" -o /tmp/s8c.py
    sed -i 's|^PAYROLL_ENTRY = .*|PAYROLL_ENTRY = "HR-PRE-2026-00001"|' /tmp/s8c.py
    bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/s8c.py').read())"
"""

from __future__ import annotations
import csv
from pathlib import Path
import frappe


# --- Edit these before running -------------------------------------------------
PAYROLL_ENTRY      = "REPLACE_WITH_PAYROLL_ENTRY_NAME"
BASELINE_CSV       = "/tmp/payroll_excel_baseline.csv"
VARIANCE_THRESHOLD = 1.0     # NGN; deltas <= 1 NGN are tolerated as rounding
# -----------------------------------------------------------------------------


# Map our reconciliation buckets <-> Salary Slip component columns
EARNING_LIKE = {"Basic", "Housing", "Transport", "Leave Allowance", "13th Month",
                "Other Allowance", "Meal Allowance", "Utility"}
DEDUCTION_BUCKETS = {
    "paye":       {"PAYE"},
    "pension_ee": {"Pension Employee", "Pension EE"},
    "nhf":        {"NHF"},
    "nhis":       {"NHIS"},
}


def load_baseline(path: str) -> dict[str, dict]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Excel baseline not found: {path}")
    out: dict[str, dict] = {}
    with p.open("r", encoding="utf-8-sig") as f:
        rdr = csv.DictReader(f)
        for r in rdr:
            emp = (r.get("employee") or "").strip()
            if not emp:
                continue
            try:
                out[emp] = {
                    "gross":      float((r.get("gross")      or 0) or 0),
                    "paye":       float((r.get("paye")       or 0) or 0),
                    "pension_ee": float((r.get("pension_ee") or 0) or 0),
                    "nhf":        float((r.get("nhf")        or 0) or 0),
                    "nhis":       float((r.get("nhis")       or 0) or 0),
                    "net":        float((r.get("net")        or 0) or 0),
                }
            except ValueError:
                continue
    return out


def fetch_erp_slips(payroll_entry: str) -> dict[str, dict]:
    rows = frappe.db.sql("""
        select name, employee, employee_name, gross_pay, total_deduction, net_pay
        from `tabSalary Slip`
        where payroll_entry = %s
          and docstatus < 2
    """, (payroll_entry,), as_dict=True)
    if not rows:
        return {}

    # Pull all earnings + deductions in two flat queries
    slip_names = [r["name"] for r in rows]
    earnings = frappe.db.sql("""
        select parent, salary_component, amount
        from `tabSalary Detail`
        where parent in %s and parentfield='earnings'
    """, (slip_names,), as_dict=True)
    deductions = frappe.db.sql("""
        select parent, salary_component, amount
        from `tabSalary Detail`
        where parent in %s and parentfield='deductions'
    """, (slip_names,), as_dict=True)

    by_slip: dict[str, dict] = {r["name"]: {**r, "earn": {}, "ded": {}} for r in rows}
    for e in earnings:
        by_slip[e["parent"]]["earn"][e["salary_component"]] = float(e["amount"] or 0)
    for d in deductions:
        by_slip[d["parent"]]["ded"][d["salary_component"]] = float(d["amount"] or 0)

    out: dict[str, dict] = {}
    for slip in by_slip.values():
        bucket_ded = {k: 0.0 for k in DEDUCTION_BUCKETS}
        for comp, amt in slip["ded"].items():
            for bucket, names in DEDUCTION_BUCKETS.items():
                if comp in names:
                    bucket_ded[bucket] += amt
                    break
        out[slip["employee"]] = {
            "slip_name":     slip["name"],
            "employee_name": slip["employee_name"],
            "gross":         float(slip["gross_pay"] or 0),
            "paye":          bucket_ded["paye"],
            "pension_ee":    bucket_ded["pension_ee"],
            "nhf":           bucket_ded["nhf"],
            "nhis":          bucket_ded["nhis"],
            "net":           float(slip["net_pay"] or 0),
        }
    return out


def main():
    print("=" * 72)
    print(f" Phase 6 / Step 8c -- Reconcile ERP vs Excel | {PAYROLL_ENTRY}")
    print("=" * 72)

    if PAYROLL_ENTRY == "REPLACE_WITH_PAYROLL_ENTRY_NAME":
        print("  ! Edit PAYROLL_ENTRY at top of script first")
        return
    if not frappe.db.exists("Payroll Entry", PAYROLL_ENTRY):
        print(f"  ! Payroll Entry {PAYROLL_ENTRY!r} not found")
        return

    try:
        baseline = load_baseline(BASELINE_CSV)
    except FileNotFoundError as e:
        print(f"  ! {e}")
        print("    Place the Excel-exported CSV at the path above and re-run.")
        return

    erp = fetch_erp_slips(PAYROLL_ENTRY)
    if not erp:
        print(f"  ! No Salary Slips found under {PAYROLL_ENTRY}")
        return

    print(f"  Excel baseline: {len(baseline)} rows | ERP slips: {len(erp)}")

    # Reconcile
    fields = ["gross", "paye", "pension_ee", "nhf", "nhis", "net"]
    rows: list[dict] = []
    only_in_excel = sorted(set(baseline.keys()) - set(erp.keys()))
    only_in_erp   = sorted(set(erp.keys())      - set(baseline.keys()))
    common        = sorted(set(erp.keys())      & set(baseline.keys()))

    over_threshold = 0
    abs_totals = {f: {"erp": 0.0, "xls": 0.0, "delta": 0.0} for f in fields}

    for emp in common:
        b = baseline[emp]
        e = erp[emp]
        deltas = {f: e[f] - b[f] for f in fields}
        for f in fields:
            abs_totals[f]["erp"]   += e[f]
            abs_totals[f]["xls"]   += b[f]
            abs_totals[f]["delta"] += deltas[f]
        flagged = any(abs(deltas[f]) > VARIANCE_THRESHOLD for f in fields)
        if flagged:
            over_threshold += 1
        rows.append({
            "employee": emp,
            "name": e["employee_name"],
            "slip": e["slip_name"],
            "erp_gross":   round(e["gross"], 2),
            "xls_gross":   round(b["gross"], 2),
            "d_gross":     round(deltas["gross"], 2),
            "erp_paye":    round(e["paye"], 2),
            "xls_paye":    round(b["paye"], 2),
            "d_paye":      round(deltas["paye"], 2),
            "erp_pension": round(e["pension_ee"], 2),
            "xls_pension": round(b["pension_ee"], 2),
            "d_pension":   round(deltas["pension_ee"], 2),
            "erp_nhf":     round(e["nhf"], 2),
            "xls_nhf":     round(b["nhf"], 2),
            "d_nhf":       round(deltas["nhf"], 2),
            "erp_nhis":    round(e["nhis"], 2),
            "xls_nhis":    round(b["nhis"], 2),
            "d_nhis":      round(deltas["nhis"], 2),
            "erp_net":     round(e["net"], 2),
            "xls_net":     round(b["net"], 2),
            "d_net":       round(deltas["net"], 2),
            "flagged":     "YES" if flagged else "",
        })

    # CSV
    csv_path = Path("/tmp/step8c_reconciliation.csv")
    if rows:
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

    # Markdown summary
    md: list[str] = []
    md.append(f"# Step 8c -- Reconciliation Report ({PAYROLL_ENTRY})")
    md.append("")
    md.append(f"_Generated: {frappe.utils.now_datetime()} | Threshold: NGN {VARIANCE_THRESHOLD:,.2f}_")
    md.append("")
    md.append("## Coverage")
    md.append("")
    md.append(f"  Employees in Excel  : {len(baseline)}")
    md.append(f"  Employees in ERP    : {len(erp)}")
    md.append(f"  Reconciled (common) : {len(common)}")
    md.append(f"  Only in Excel       : {len(only_in_excel)}")
    md.append(f"  Only in ERP         : {len(only_in_erp)}")
    md.append("")
    md.append("## Aggregate Comparison")
    md.append("")
    md.append("  | Field      |        ERP |      Excel |        Delta |")
    md.append("  |------------|-----------:|-----------:|-------------:|")
    for f in fields:
        a = abs_totals[f]
        md.append(f"  | {f:<10} | {a['erp']:>10,.2f} | {a['xls']:>10,.2f} | {a['delta']:>+12,.2f} |")
    md.append("")
    md.append(f"## Flagged employees (> NGN {VARIANCE_THRESHOLD:,.2f}): {over_threshold}")
    md.append("")
    if over_threshold:
        md.append("  See `/tmp/step8c_reconciliation.csv` (column `flagged`) for the full list.")
        md.append("")
        # Top 15 worst offenders by absolute net delta
        worst = sorted(rows, key=lambda r: abs(r["d_net"]), reverse=True)[:15]
        md.append("  **Top 15 by abs(net delta):**")
        md.append("")
        md.append("  | Employee | Name | ERP Net | Excel Net | Delta |")
        md.append("  |----------|------|--------:|----------:|------:|")
        for r in worst:
            md.append(f"  | {r['employee']} | {r['name']} | "
                      f"{r['erp_net']:>10,.2f} | {r['xls_net']:>10,.2f} | {r['d_net']:>+10,.2f} |")
        md.append("")
    if only_in_excel:
        md.append("## Only in Excel (no ERP slip)")
        md.append("")
        for emp in only_in_excel[:50]:
            md.append(f"  - {emp}")
        if len(only_in_excel) > 50:
            md.append(f"  ... +{len(only_in_excel)-50} more (see CSV)")
        md.append("")
    if only_in_erp:
        md.append("## Only in ERP (no Excel baseline row)")
        md.append("")
        for emp in only_in_erp[:50]:
            md.append(f"  - {emp} ({erp[emp]['employee_name']})")
        if len(only_in_erp) > 50:
            md.append(f"  ... +{len(only_in_erp)-50} more (see CSV)")
        md.append("")

    md_path = Path("/tmp/step8c_reconciliation.md")
    md_path.write_text("\n".join(md), encoding="utf-8")

    # Register File docs (private)
    import base64
    for p in (md_path, csv_path):
        if not p.exists():
            continue
        try:
            content = p.read_bytes()
            frappe.get_doc({
                "doctype": "File",
                "file_name": p.name,
                "is_private": 1,
                "content": base64.b64encode(content).decode(),
                "decode": True,
            }).insert(ignore_permissions=True)
        except Exception:
            pass
    frappe.db.commit()

    print()
    for line in md:
        print(line)
    print()
    print(f"[OK] {csv_path}")
    print(f"[OK] {md_path}")
    if over_threshold == 0:
        print()
        print(">>> CLEAN: No variances > threshold. Payroll Entry is ready for workflow approval.")
    else:
        print()
        print(f">>> {over_threshold} flagged rows. Review CSV before submitting Payroll Entry.")


try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
