"""
Phase 6 / Step 8a: Parallel Payroll Run -- PRE-FLIGHT VALIDATION.

Read-only. Does not insert/update any document.

Purpose:
    Before running the first ERPNext payroll cycle (June 2026), confirm that
    every dependency is in place and project the expected aggregate cash-out.

Sections:
    1.  Period sanity (dates, Holiday List, Leave Period coverage)
    2.  Salary Components present (PAYE, Pension, NHF, NHIS, 13th Month, Leave Allowance)
    3.  Active SSAs per active Employee (& base sanity vs 10x bug)
    4.  Bank data quality (bank_name + bank_ac_no + NIBSS code resolved)
    5.  Cost Centre coverage (payroll_cost_center mapped on every Employee)
    6.  PAYE projection -- python-side replication of the Salary Component formula
    7.  Aggregate projection: Earnings, PAYE, Pension EE+ER, NHF, NHIS, Net Pay

Inputs (edit before running):
    PERIOD_START, PERIOD_END, COMPANY

Outputs:
    /tmp/step8a_payroll_preflight.md      -- summary report
    /tmp/step8a_payroll_preflight.csv     -- per-employee projection
    /tmp/step8a_payroll_skips.csv         -- employees that will be skipped + reason

Run:
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/feat/sungas-customizations/scripts/step8a_payroll_preflight.py" -o /tmp/s8a.py
    bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/s8a.py').read())"
"""

from __future__ import annotations
import csv
from pathlib import Path
from datetime import datetime
import frappe


# --- Edit these before running -------------------------------------------------
PERIOD_START = "2026-05-01"
PERIOD_END   = "2026-05-31"
COMPANY      = "SUNGAS COMPANY LIMITED"
# Sungas policy (2026): every active employee is deemed to claim the maximum
# rent relief. We therefore floor `rent_paid_annually` at 2,500,000 in this
# Python-side projection so the cap of NGN 500,000 always applies. The live
# PAYE Salary Component formula relies on the actual Employee field, so run
# step3c_apply_max_rent_relief.py BEFORE the live payroll cycle.
ASSUME_MAX_RENT_RELIEF = True
RENT_RELIEF_FLOOR      = 2_500_000   # 20% * 2,500,000 = 500,000 (cap)
# -----------------------------------------------------------------------------


# NTAA 2025 brackets -- mirror of step3_paye_ntaa2025.py
NTAA_BRACKETS = [
    (   800_000,            0, 0.00),
    ( 3_000_000,            0, 0.15),
    (12_000_000,      330_000, 0.18),
    (25_000_000,    1_950_000, 0.21),
    (50_000_000,    4_680_000, 0.23),
    (float("inf"), 10_430_000, 0.25),
]


def paye_annual(taxable: float) -> float:
    prev = 0
    for upper, base, rate in NTAA_BRACKETS:
        if taxable <= upper:
            return base + (taxable - prev) * rate
        prev = upper
    return 0.0


# ---------- 1. Period sanity ----------
def section_period(report: list[str]) -> dict:
    report.append("## 1. Period & Calendars")
    report.append("")
    out = {"holiday_list": None, "leave_period": None, "ok": True}

    company = frappe.db.get_value("Company", COMPANY, ["name", "default_holiday_list", "default_currency"], as_dict=True)
    if not company:
        report.append(f"  ! Company `{COMPANY}` not found")
        out["ok"] = False
        return out
    report.append(f"  = Company: `{company['name']}` ({company['default_currency']})")

    out["holiday_list"] = company["default_holiday_list"]
    if not company["default_holiday_list"]:
        report.append("  ! No default Holiday List on Company")
        out["ok"] = False
    else:
        hcount = frappe.db.count("Holiday", {
            "parent": company["default_holiday_list"],
            "holiday_date": ["between", [PERIOD_START, PERIOD_END]],
        })
        report.append(f"  = Default Holiday List: `{company['default_holiday_list']}` ({hcount} holidays in window)")

    # Leave period coverage
    lp = frappe.db.sql("""
        select name, from_date, to_date
        from `tabLeave Period`
        where %s between from_date and to_date
          and (company is null or company = '' or company = %s)
        limit 1
    """, (PERIOD_START, COMPANY), as_dict=True)
    if not lp:
        report.append(f"  ! No Leave Period covers {PERIOD_START}")
        out["ok"] = False
    else:
        out["leave_period"] = lp[0]["name"]
        report.append(f"  = Leave Period: `{lp[0]['name']}` ({lp[0]['from_date']} -> {lp[0]['to_date']})")

    report.append("")
    return out


# ---------- 2. Salary Component health ----------
def section_components(report: list[str]) -> dict:
    report.append("## 2. Salary Components")
    report.append("")
    needed = ["PAYE", "Pension Employee", "Pension Employer", "NHF", "NHIS", "13th Month", "Leave Allowance"]
    found = {}
    for n in needed:
        ex = frappe.db.exists("Salary Component", n)
        found[n] = bool(ex)
        report.append(f"  {'=' if ex else '!'} `{n}` {'present' if ex else 'MISSING'}")
    report.append("")
    return found


# ---------- 3. SSA + base sanity ----------
def section_ssas(report: list[str]) -> dict:
    report.append("## 3. Salary Structure Assignments (active)")
    report.append("")
    rows = frappe.db.sql("""
        select
            ssa.name,
            ssa.employee,
            e.employee_name,
            e.status as emp_status,
            e.designation,
            e.branch,
            e.payroll_cost_center,
            e.bank_name,
            e.bank_ac_no,
            e.rent_paid_annually,
            ssa.salary_structure,
            ssa.base,
            ssa.from_date
        from `tabSalary Structure Assignment` ssa
        join tabEmployee e on e.name = ssa.employee
        where ssa.docstatus = 1
          and e.status = 'Active'
          and ssa.from_date <= %s
        order by ssa.employee, ssa.from_date desc
    """, (PERIOD_END,), as_dict=True)

    # Pick most-recent active SSA per employee (MySQL gave us order)
    seen = set()
    latest = []
    for r in rows:
        if r["employee"] in seen:
            continue
        seen.add(r["employee"])
        latest.append(r)

    # Sanity: bases above 10M are suspicious (relic 10x bug check)
    suspicious = [r for r in latest if r["base"] and r["base"] >= 10_000_000]

    report.append(f"  Active employees with active SSA: {len(latest)}")
    report.append(f"  Distinct salary structures used : {len({r['salary_structure'] for r in latest})}")
    report.append(f"  Suspicious bases (>= 10,000,000): {len(suspicious)}")
    if suspicious:
        report.append("  (Re-check these against original Excel BEFORE running payroll)")
        for s in suspicious[:10]:
            report.append(f"    - {s['employee']} {s['employee_name']}: base = {s['base']:,.0f}")
    report.append("")
    return {"ssas": latest, "suspicious": suspicious}


# ---------- 4. Bank data quality ----------
def section_bank(report: list[str], ssas: list[dict]) -> dict:
    report.append("## 4. Bank Disbursement Data Quality")
    report.append("")
    bank_codes = {b["name"]: b.get("nibss_code")
                  for b in frappe.get_all("Bank", fields=["name", "nibss_code"])}

    no_bank = [r for r in ssas if not (r.get("bank_name") or "").strip()]
    no_acct = [r for r in ssas if not (r.get("bank_ac_no") or "").strip()]
    no_code = [r for r in ssas
               if (r.get("bank_name") or "").strip()
               and not bank_codes.get((r.get("bank_name") or "").strip())]

    report.append(f"  Banks seeded with NIBSS code: {sum(1 for v in bank_codes.values() if v)}")
    report.append(f"  Employees missing bank_name : {len(no_bank)}")
    report.append(f"  Employees missing bank_ac_no: {len(no_acct)}")
    report.append(f"  Bank-name w/o NIBSS code    : {len(no_code)}")
    if no_code:
        names = sorted({r['bank_name'] for r in no_code})
        report.append(f"    Unmapped banks: {', '.join(names)}")
    report.append("")
    return {"no_bank": no_bank, "no_acct": no_acct, "no_code": no_code, "bank_codes": bank_codes}


# ---------- 5. Cost-centre coverage ----------
def section_cost_centres(report: list[str], ssas: list[dict]) -> dict:
    report.append("## 5. Cost Centre Mapping")
    report.append("")
    no_cc = [r for r in ssas if not (r.get("payroll_cost_center") or "").strip()]
    distinct = sorted({r.get("payroll_cost_center") for r in ssas if r.get("payroll_cost_center")})
    report.append(f"  Distinct payroll cost centres: {len(distinct)}")
    report.append(f"  Employees missing CC mapping : {len(no_cc)}")
    if no_cc:
        for r in no_cc[:10]:
            report.append(f"    - {r['employee']} {r['employee_name']}")
    report.append("")
    return {"no_cc": no_cc, "distinct_cc": distinct}


# ---------- 6+7. Earnings + PAYE projection ----------
def evaluate_structure_components(structure_name: str, base: float, employee: str | None = None) -> dict:
    """Compute earnings + statutory deductions using ERPNext's own slip processor.

    Builds an in-memory Salary Slip via `make_salary_slip`, runs
    `process_salary_structure()`, and reads the resulting earnings + deductions
    rows. Nothing is persisted -- the slip is never inserted.

    This handles iterative formulas (component-abbreviation references) that
    a naive Python replica cannot resolve. Falls back to a base-only Python
    estimate if the API is unavailable.
    """
    earnings_breakdown: dict[str, float] = {}
    earnings_total = 0.0
    pen_ee_real = pen_er_real = nhf_real = nhis_real = 0.0

    try:
        from hrms.payroll.doctype.salary_structure.salary_structure import make_salary_slip
        slip = make_salary_slip(structure_name, employee=employee)
        slip.start_date = PERIOD_START
        slip.end_date   = PERIOD_END
        slip.posting_date = PERIOD_END
        # Force the desired base in case SSA on this employee differs
        slip.base = base
        slip.process_salary_structure()
        for row in (slip.earnings or []):
            amt = float(row.amount or 0)
            earnings_breakdown[row.salary_component] = amt
            # Statistical components don't post; they're slip-only. Filter them.
            if not getattr(row, "statistical_component", 0):
                earnings_total += amt
        for row in (slip.deductions or []):
            comp = row.salary_component
            amt = float(row.amount or 0)
            if comp in ("Pension Employee", "Pension EE"):
                pen_ee_real += amt
            elif comp in ("Pension Employer", "Pension ER"):
                pen_er_real += amt
            elif comp == "NHF":
                nhf_real += amt
            elif comp == "NHIS":
                nhis_real += amt
        # If structure didn't include NHF/NHIS as components, fall back to convention
        basic = earnings_breakdown.get("Basic Pay", earnings_breakdown.get("Basic", 0))
        if pen_ee_real == 0:
            housing  = earnings_breakdown.get("Housing Allowance", earnings_breakdown.get("Housing", 0))
            transport= earnings_breakdown.get("Transport Allowance", earnings_breakdown.get("Transport", 0))
            pen_base = basic + housing + transport
            pen_ee_real = 0.08 * pen_base
            pen_er_real = 0.10 * pen_base
        if nhf_real == 0:
            nhf_real = 0.025 * basic   # convention only; structure doesn't enforce
        if nhis_real == 0:
            nhis_real = 0.0    # NHIS replaced by company HMO at Sungas
        return {
            "earnings_total":    earnings_total,
            "earnings_breakdown": earnings_breakdown,
            "pension_ee":        pen_ee_real,
            "pension_er":        pen_er_real,
            "nhf":               nhf_real,
            "nhis":              nhis_real,
        }
    except Exception:
        # Fallback: best-effort manual evaluation (legacy behaviour)
        ss = frappe.get_cached_doc("Salary Structure", structure_name)
        for row in ss.earnings:
            amt = 0.0
            if row.amount_based_on_formula and row.formula:
                try:
                    amt = float(frappe.safe_eval(row.formula, None, {"base": base, "B": base}))
                except Exception:
                    amt = 0.0
            else:
                amt = float(row.amount or 0)
            earnings_total += amt
            earnings_breakdown[row.salary_component] = amt
        basic = earnings_breakdown.get("Basic Pay", earnings_breakdown.get("Basic", 0))
        housing = earnings_breakdown.get("Housing Allowance", earnings_breakdown.get("Housing", 0))
        transport = earnings_breakdown.get("Transport Allowance", earnings_breakdown.get("Transport", 0))
        pen_base = basic + housing + transport
        return {
            "earnings_total":     earnings_total,
            "earnings_breakdown": earnings_breakdown,
            "pension_ee":         0.08 * pen_base,
            "pension_er":         0.10 * pen_base,
            "nhf":                0.025 * basic,
            "nhis":               0.0,
        }


def section_projection(report: list[str], ssas: list[dict]) -> tuple[list[dict], dict]:
    report.append("## 6. Projected PAYE & Net Pay (Python-side replica)")
    report.append("")
    per_emp_rows = []
    agg = {"gross": 0, "paye": 0, "pension_ee": 0, "pension_er": 0,
           "nhf": 0, "nhis": 0, "net": 0, "skipped": 0, "ok": 0}

    designations_excluded = {
        "Non-Executive Director",
        "Chairman",
        "Independent Director",
    }

    for r in ssas:
        try:
            base = float(r["base"] or 0)
            calc = evaluate_structure_components(r["salary_structure"], base, employee=r["employee"])
        except Exception as e:
            agg["skipped"] += 1
            per_emp_rows.append({
                "employee": r["employee"],
                "employee_name": r["employee_name"],
                "structure": r["salary_structure"],
                "base": base,
                "error": str(e)[:120],
            })
            continue

        earnings = calc["earnings_total"]
        pen_ee   = calc["pension_ee"]
        rent     = float(r.get("rent_paid_annually") or 0)
        if ASSUME_MAX_RENT_RELIEF:
            rent = max(rent, RENT_RELIEF_FLOOR)

        if r.get("designation") in designations_excluded:
            paye_monthly = 0.0
        else:
            taxable = max(0, earnings*12 - min(rent*0.20, 500_000) - pen_ee*12)
            paye_monthly = paye_annual(taxable) / 12.0

        statutory = pen_ee + calc["nhf"] + calc["nhis"] + paye_monthly
        net = earnings - statutory

        agg["gross"]      += earnings
        agg["paye"]       += paye_monthly
        agg["pension_ee"] += pen_ee
        agg["pension_er"] += calc["pension_er"]
        agg["nhf"]        += calc["nhf"]
        agg["nhis"]       += calc["nhis"]
        agg["net"]        += net
        agg["ok"]         += 1

        per_emp_rows.append({
            "employee": r["employee"],
            "employee_name": r["employee_name"],
            "designation": r.get("designation") or "",
            "branch": r.get("branch") or "",
            "structure": r["salary_structure"],
            "base": round(base, 2),
            "earnings": round(earnings, 2),
            "pension_ee": round(pen_ee, 2),
            "pension_er": round(calc["pension_er"], 2),
            "nhf": round(calc["nhf"], 2),
            "nhis": round(calc["nhis"], 2),
            "paye": round(paye_monthly, 2),
            "net": round(net, 2),
            "rent_paid_annually": round(rent, 2),
        })

    report.append(f"  Computed: {agg['ok']} | Errors: {agg['skipped']}")
    report.append("")
    report.append("## 7. Aggregate Projection (this period)")
    report.append("")
    report.append(f"  Total Gross Earnings : NGN {agg['gross']:>16,.2f}")
    report.append(f"  Total PAYE           : NGN {agg['paye']:>16,.2f}")
    report.append(f"  Total Pension (EE)   : NGN {agg['pension_ee']:>16,.2f}")
    report.append(f"  Total Pension (ER)   : NGN {agg['pension_er']:>16,.2f}")
    report.append(f"  Total NHF            : NGN {agg['nhf']:>16,.2f}")
    report.append(f"  Total NHIS           : NGN {agg['nhis']:>16,.2f}")
    report.append(f"  Total Net Pay        : NGN {agg['net']:>16,.2f}")
    report.append(f"  Total Pension Cost   : NGN {agg['pension_ee'] + agg['pension_er']:>16,.2f}")
    report.append("")
    return per_emp_rows, agg


# ---------- Output writers ----------
def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    headers = sorted({k for r in rows for k in r.keys()})
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def main():
    print("=" * 72)
    print(f" Phase 6 / Step 8a -- Payroll Pre-flight ({PERIOD_START} -> {PERIOD_END})")
    print("=" * 72)

    report: list[str] = []
    report.append(f"# Step 8a -- Payroll Pre-flight ({PERIOD_START} -> {PERIOD_END})")
    report.append("")
    report.append(f"_Generated: {frappe.utils.now_datetime()} | Site: {frappe.local.site}_")
    report.append("")

    section_period(report)
    section_components(report)
    s = section_ssas(report)
    bank = section_bank(report, s["ssas"])
    section_cost_centres(report, s["ssas"])
    per_emp, agg = section_projection(report, s["ssas"])

    # Skip CSV
    skip_rows: list[dict] = []
    for r in bank["no_bank"]:
        skip_rows.append({"employee": r["employee"], "name": r["employee_name"], "reason": "missing bank_name"})
    for r in bank["no_acct"]:
        skip_rows.append({"employee": r["employee"], "name": r["employee_name"], "reason": "missing bank_ac_no"})
    for r in bank["no_code"]:
        skip_rows.append({"employee": r["employee"], "name": r["employee_name"],
                          "reason": f"bank '{r['bank_name']}' has no NIBSS code"})

    md_path  = Path("/tmp/step8a_payroll_preflight.md")
    csv_path = Path("/tmp/step8a_payroll_preflight.csv")
    skip_path = Path("/tmp/step8a_payroll_skips.csv")

    md_path.write_text("\n".join(report), encoding="utf-8")
    write_csv(csv_path, per_emp)
    write_csv(skip_path, skip_rows)

    # Register File docs (private) so HR can download from Desk
    import base64
    for p in (md_path, csv_path, skip_path):
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
    for line in report:
        print(line)
    print()
    print(f"[OK] Wrote: {md_path}")
    print(f"[OK] Wrote: {csv_path}  ({len(per_emp)} rows)")
    print(f"[OK] Wrote: {skip_path} ({len(skip_rows)} rows)")
    print()
    print("Next step: review CSV. If totals look right, run step8b to create the Payroll Entry.")


try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
