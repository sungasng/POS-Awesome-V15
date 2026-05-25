"""
Phase 6 / Step 8c -- Reconcile ERP Salary Slips vs Excel baseline.

Compares Net Pay (and optionally Gross / PAYE / Pension EE) between:
  - ERP: all Salary Slips on a Payroll Entry
  - Excel: the legacy 'STAFF PAYROLL FOR MAY 2026.xls' workbook
           (one sheet per location; columns: Name, Gross, Basic, Transport,
            Housing, Cola, Medical, NSITF, Pension ER, Pension EE, PAYE,
            Total Earning, Total Deduction, Net Pay, etc.)

Matching is fuzzy on full name (token set Jaccard >= 0.80) because:
  - Excel: "ABANIKANDA FEMI"      ERP: "FEMI Abanikanda"
  - Excel: "AYO AKINBOBOLA"       ERP: "Akinbobola AYO"
  - Excel: "BULUS SATI"           ERP: "Bulus Sati"

Off-payroll contractors (~17 in offpayroll MAY 2026.docx) are NOT in ERP,
so they naturally fall into the 'unmatched Excel' bucket -- expected.

Variances are surfaced in 4 buckets:
  1. Net Pay variance > NET_PAY_TOLERANCE (default NGN 1)
  2. Gross variance > GROSS_TOLERANCE
  3. PAYE variance > PAYE_TOLERANCE
  4. Pension EE variance > PEN_EE_TOLERANCE

Inputs (edit before running):
  PAYROLL_ENTRY      -- ERP PE name (e.g. 'HR-PRUN-2026-00001')
  EXCEL_PATH         -- local path on the bench. Default downloads from URL.
  EXCEL_URL          -- public URL (used if EXCEL_PATH does not exist)

Read-only. Writes report to /tmp/step8c_reconciliation.md and prints to stdout.

Run:
    SHA=<commit>
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/$SHA/scripts/step8c_payroll_reconcile.py" -o /tmp/s8c.py
    bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/s8c.py').read())"

Dependencies:
  pip install 'xlrd==1.2.0'   # legacy .xls reader
  (script will auto-pip-install into the bench venv if missing)
"""

from __future__ import annotations
import os
import re
import sys
import urllib.request
from pathlib import Path
import frappe


# ---- Edit before running ----------------------------------------------------
PAYROLL_ENTRY     = "HR-PRUN-2026-00001"
EXCEL_PATH        = "/tmp/payroll_excel_baseline.xls"
EXCEL_URL         = ("https://customer-assets.emergentagent.com/job_nextgen-erp-6/"
                     "artifacts/pop5ckua_STAFF%20PAYROLL%20FOR%20MAY%202026.xls")
NET_PAY_TOLERANCE = 1.00       # NGN
GROSS_TOLERANCE   = 1.00
PAYE_TOLERANCE    = 1.00
PEN_EE_TOLERANCE  = 1.00
MATCH_THRESHOLD   = 0.80       # token-set Jaccard ratio
# -----------------------------------------------------------------------------

SKIP_SHEETS = {"APPROVAL MEMO", "TRANSFER 1ST BANK", "BANK TRANSFER IBTC",
               "CASH SALARY", "IBTC PENSION", "NSITF"}


def _ensure_xlrd() -> None:
    try:
        import xlrd  # noqa: F401
    except ImportError:
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install",
                               "--quiet", "xlrd==1.2.0"])


def _download_excel() -> None:
    if os.path.exists(EXCEL_PATH):
        return
    print(f"  ~ Downloading Excel: {EXCEL_URL}")
    urllib.request.urlretrieve(EXCEL_URL, EXCEL_PATH)
    print(f"  + Saved to {EXCEL_PATH}")


def _norm_tokens(name: str) -> set[str]:
    """Normalize a name to a set of tokens for fuzzy matching."""
    if not name:
        return set()
    # uppercase, strip punctuation, split
    cleaned = re.sub(r"[^A-Z0-9 ]", " ", name.upper())
    toks = {t for t in cleaned.split() if len(t) >= 2}
    return toks


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _find_header_row(sheet) -> int:
    """Find the row containing 'Name' + 'Net Pay' headers. Usually row 3."""
    for r in range(min(sheet.nrows, 8)):
        row = [str(sheet.cell_value(r, c) or "").strip().lower()
               for c in range(min(sheet.ncols, 30))]
        if "name" in row and any("net pay" in h for h in row):
            return r
    return -1


def _col_idx(headers: list[str], *needles: str) -> int:
    for i, h in enumerate(headers):
        h_clean = re.sub(r"[^a-z0-9]", "", h.lower())
        for n in needles:
            n_clean = re.sub(r"[^a-z0-9]", "", n.lower())
            if h_clean == n_clean:
                return i
    return -1


def load_excel_records() -> list[dict]:
    """Return list of {sheet, name, gross, paye, pen_ee, net_pay}."""
    import xlrd
    wb = xlrd.open_workbook(EXCEL_PATH)
    records = []

    for sname in wb.sheet_names():
        if sname.strip().upper() in SKIP_SHEETS:
            continue
        sh = wb.sheet_by_name(sname)
        hr = _find_header_row(sh)
        if hr < 0:
            continue
        headers = [str(sh.cell_value(hr, c) or "").strip() for c in range(sh.ncols)]
        idx_name   = _col_idx(headers, "Name")
        idx_gross  = _col_idx(headers, "Gross")
        idx_paye   = _col_idx(headers, "PAYEE", "PAYE")
        idx_pen_ee = _col_idx(headers, "Pension - EE", "Pension EE")
        idx_net    = _col_idx(headers, "Net Pay")
        idx_tot_de = _col_idx(headers, "Total Deduction")
        if idx_name < 0 or idx_net < 0:
            continue

        for r in range(hr + 1, sh.nrows):
            raw_name = str(sh.cell_value(r, idx_name) or "").strip()
            if not raw_name:
                continue
            # Skip totals/summary rows
            if raw_name.lower() in ("total", "totals", "sum", "grand total"):
                continue
            net = sh.cell_value(r, idx_net) if idx_net >= 0 else None
            if isinstance(net, str):
                try:
                    net = float(net.replace(",", "").strip()) if net.strip() else None
                except ValueError:
                    net = None
            if net is None or not isinstance(net, (int, float)) or net <= 0:
                continue
            def _num(c):
                v = sh.cell_value(r, c) if c >= 0 else 0
                if isinstance(v, str):
                    try:
                        return float(v.replace(",", "").strip() or 0)
                    except ValueError:
                        return 0.0
                return float(v or 0)

            records.append({
                "sheet":   sname,
                "name":    raw_name,
                "tokens":  _norm_tokens(raw_name),
                "gross":   _num(idx_gross),
                "paye":    _num(idx_paye),
                "pen_ee":  _num(idx_pen_ee),
                "net_pay": float(net),
                "tot_de":  _num(idx_tot_de),
            })
    print(f"  + Excel records loaded: {len(records)} (across {len([s for s in wb.sheet_names() if s.strip().upper() not in SKIP_SHEETS])} location sheets)")
    return records


def load_erp_records(pe_name: str) -> list[dict]:
    """Return all draft+submitted slips for the PE with their net_pay etc."""
    rows = frappe.db.sql("""
        select ss.name as slip, ss.employee, ss.employee_name,
               ss.gross_pay, ss.net_pay, ss.total_deduction,
               (select sum(amount) from `tabSalary Detail`
                where parent = ss.name and parentfield = 'deductions'
                  and salary_component = 'PAYE') as paye,
               (select sum(amount) from `tabSalary Detail`
                where parent = ss.name and parentfield = 'deductions'
                  and salary_component = 'Pension Employee') as pen_ee,
               e.branch
        from `tabSalary Slip` ss
        join tabEmployee e on e.name = ss.employee
        where ss.payroll_entry = %s
          and ss.docstatus in (0, 1)
        order by ss.employee_name
    """, (pe_name,), as_dict=True)

    for r in rows:
        r["tokens"] = _norm_tokens(r["employee_name"])
        r["paye"]   = float(r.get("paye") or 0)
        r["pen_ee"] = float(r.get("pen_ee") or 0)
    print(f"  + ERP records loaded: {len(rows)} slips for {pe_name}")
    return rows


def match(excel_recs: list[dict], erp_recs: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """Return (matches, excel_only, erp_only). Each match: {excel, erp, score}."""
    matches: list[dict] = []
    used_erp_idx: set[int] = set()

    # First pass: exact token-set equality (Jaccard = 1.0)
    for ex in excel_recs:
        best_i = -1
        best_score = 0.0
        for i, er in enumerate(erp_recs):
            if i in used_erp_idx:
                continue
            score = _jaccard(ex["tokens"], er["tokens"])
            if score > best_score:
                best_score = score
                best_i = i
        if best_i >= 0 and best_score >= MATCH_THRESHOLD:
            matches.append({"excel": ex, "erp": erp_recs[best_i], "score": best_score})
            used_erp_idx.add(best_i)

    matched_excel_ids = {id(m["excel"]) for m in matches}
    excel_only = [ex for ex in excel_recs if id(ex) not in matched_excel_ids]
    erp_only   = [er for i, er in enumerate(erp_recs) if i not in used_erp_idx]

    return matches, excel_only, erp_only


def variance(matches: list[dict]) -> dict:
    """Bucket variances by component."""
    out = {"net": [], "gross": [], "paye": [], "pen_ee": []}
    for m in matches:
        ex, er = m["excel"], m["erp"]
        d_net   = round(float(er["net_pay"])  - float(ex["net_pay"]),   2)
        d_gross = round(float(er["gross_pay"]) - float(ex["gross"]),    2)
        d_paye  = round(float(er["paye"])      - float(ex["paye"]),     2)
        d_pen   = round(float(er["pen_ee"])    - float(ex["pen_ee"]),   2)
        row = {"excel": ex, "erp": er, "d_net": d_net, "d_gross": d_gross,
               "d_paye": d_paye, "d_pen": d_pen, "score": m["score"]}
        if abs(d_net) > NET_PAY_TOLERANCE:
            out["net"].append(row)
        if abs(d_gross) > GROSS_TOLERANCE:
            out["gross"].append(row)
        if abs(d_paye) > PAYE_TOLERANCE:
            out["paye"].append(row)
        if abs(d_pen) > PEN_EE_TOLERANCE:
            out["pen_ee"].append(row)
    for k in out:
        out[k].sort(key=lambda r: abs(r[f"d_{ 'net' if k=='net' else 'gross' if k=='gross' else 'paye' if k=='paye' else 'pen' }"]), reverse=True)
    return out


def main() -> None:
    print("=" * 72)
    print(f" Phase 6 / Step 8c -- Reconcile {PAYROLL_ENTRY} vs Excel baseline")
    print("=" * 72)

    if not frappe.db.exists("Payroll Entry", PAYROLL_ENTRY):
        print(f"  ! Payroll Entry '{PAYROLL_ENTRY}' not found.")
        return

    _ensure_xlrd()
    _download_excel()

    excel_recs = load_excel_records()
    erp_recs   = load_erp_records(PAYROLL_ENTRY)
    matches, excel_only, erp_only = match(excel_recs, erp_recs)
    var = variance(matches)

    sum_excel_net = sum(ex["net_pay"] for ex in excel_recs)
    sum_erp_net   = sum(er["net_pay"] for er in erp_recs)
    sum_match_excel = sum(m["excel"]["net_pay"] for m in matches)
    sum_match_erp   = sum(m["erp"]["net_pay"]   for m in matches)

    # ---- summary ----
    lines = []
    lines.append(f"# Step 8c -- Reconciliation: {PAYROLL_ENTRY}")
    lines.append("")
    lines.append("## Counts")
    lines.append(f"- Excel rows           : {len(excel_recs)}")
    lines.append(f"- ERP slips            : {len(erp_recs)}")
    lines.append(f"- Matched              : {len(matches)}")
    lines.append(f"- Excel only (no ERP)  : {len(excel_only)}  (incl. off-payroll contractors)")
    lines.append(f"- ERP only (no Excel)  : {len(erp_only)}")
    lines.append("")
    lines.append("## Net Pay Totals (NGN)")
    lines.append(f"- Excel total       : {sum_excel_net:>16,.2f}")
    lines.append(f"- ERP total         : {sum_erp_net:>16,.2f}")
    lines.append(f"- Matched-Excel sum : {sum_match_excel:>16,.2f}")
    lines.append(f"- Matched-ERP   sum : {sum_match_erp:>16,.2f}")
    lines.append(f"- Matched diff      : {sum_match_erp - sum_match_excel:>+16,.2f}")
    lines.append("")
    lines.append(f"## Variances > tolerance (Net={NET_PAY_TOLERANCE} | Gross={GROSS_TOLERANCE} | PAYE={PAYE_TOLERANCE} | PenEE={PEN_EE_TOLERANCE})")
    lines.append(f"- Net Pay  : {len(var['net'])}")
    lines.append(f"- Gross    : {len(var['gross'])}")
    lines.append(f"- PAYE     : {len(var['paye'])}")
    lines.append(f"- PenEE    : {len(var['pen_ee'])}")
    lines.append("")

    # ---- detail tables (top 50 per bucket) ----
    for bucket, header in [("net", "Net Pay"), ("gross", "Gross Pay"),
                           ("paye", "PAYE"), ("pen_ee", "Pension EE")]:
        if not var[bucket]:
            continue
        lines.append(f"### {header} variances (top 50)")
        lines.append("")
        lines.append(f"| Sheet | Excel name | ERP name | ERP slip | Excel {header} | ERP {header} | Diff |")
        lines.append("|---|---|---|---|---:|---:|---:|")
        for r in var[bucket][:50]:
            ex, er = r["excel"], r["erp"]
            ex_v = ex["net_pay"] if bucket == "net" else ex["gross"] if bucket == "gross" else ex["paye"] if bucket == "paye" else ex["pen_ee"]
            er_v = er["net_pay"] if bucket == "net" else er["gross_pay"] if bucket == "gross" else er["paye"] if bucket == "paye" else er["pen_ee"]
            d    = r[f"d_{'net' if bucket=='net' else 'gross' if bucket=='gross' else 'paye' if bucket=='paye' else 'pen'}"]
            lines.append(f"| {ex['sheet']} | {ex['name']} | {er['employee_name']} | {er['slip']} "
                         f"| {ex_v:>12,.2f} | {er_v:>12,.2f} | {d:>+12,.2f} |")
        lines.append("")

    # ---- Excel-only roster ----
    if excel_only:
        lines.append("## Excel-only (no ERP match) — incl. off-payroll contractors")
        lines.append("")
        lines.append("| Sheet | Name | Excel Net Pay |")
        lines.append("|---|---|---:|")
        for ex in sorted(excel_only, key=lambda x: x["sheet"]):
            lines.append(f"| {ex['sheet']} | {ex['name']} | {ex['net_pay']:>12,.2f} |")
        lines.append("")

    # ---- ERP-only roster ----
    if erp_only:
        lines.append("## ERP-only (no Excel match)")
        lines.append("")
        lines.append("| ERP name | Slip | Branch | ERP Net Pay |")
        lines.append("|---|---|---|---:|")
        for er in sorted(erp_only, key=lambda x: x["employee_name"]):
            lines.append(f"| {er['employee_name']} | {er['slip']} | {er.get('branch') or '—'} | {er['net_pay']:>12,.2f} |")
        lines.append("")

    report = "\n".join(lines)
    Path("/tmp/step8c_reconciliation.md").write_text(report, encoding="utf-8")
    print()
    print(report)
    print()
    print("  Full report: /tmp/step8c_reconciliation.md")


try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
