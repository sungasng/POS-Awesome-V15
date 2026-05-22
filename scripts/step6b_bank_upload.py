"""
Phase 6 / Step 6b: Bank Upload File Generator.

Generates payroll bank-upload CSVs from a submitted Payroll Entry, in the
exact format expected by Stanbic IBTC and Fidelity Bank.

Stanbic IBTC format (xlsx; we generate CSV equivalent):
    Reciever Name | Reciever Account No | Amount | Sender |
    Narration | Receiever's Narration | BankCode

Fidelity format (CSV, comma-delimited, double-quoted):
    Beneficiary Bank Code,Beneficiary Account Number ,Beneficiary Name,
    Amount,Narration(Must be between 5 to 47 Characters)

Inputs:
    - PAYROLL_ENTRY: name of the submitted Payroll Entry
    - BANK: 'STANBIC' or 'FIDELITY'

Outputs:
    /tmp/bank_upload_<bank>_<payroll_entry>.csv

Pre-requisites (HR data quality):
    Each Employee must have:
      - bank_name set (and the Bank doctype record must have nibss_code)
      - bank_ac_no set
    Otherwise the row is skipped and listed in the report.

Run:
    curl -fsSL "<raw url>/scripts/step6b_bank_upload.py" -o /tmp/s6b.py
    # Edit PAYROLL_ENTRY + BANK at top of file:
    sed -i 's/^PAYROLL_ENTRY = .*/PAYROLL_ENTRY = "HR-PRE-2026-00001"/' /tmp/s6b.py
    sed -i 's/^BANK = .*/BANK = "STANBIC"/' /tmp/s6b.py
    bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/s6b.py').read())"
"""

from __future__ import annotations
import csv
from pathlib import Path
import frappe


# --- Edit these two before running ---
PAYROLL_ENTRY = "REPLACE_WITH_PAYROLL_ENTRY_NAME"
BANK = "STANBIC"  # STANBIC or FIDELITY
# --------------------------------------

# Sender bank account name shown in Stanbic file (col "Sender")
SENDER_NAME = "SUNGAS COMPANY LIMITED"


def fetch_slip_rows(payroll_entry: str) -> list[dict]:
    """Return list of dicts with employee + bank + net_pay for each Salary Slip."""
    rows = frappe.db.sql("""
        select
            ss.name as slip_name,
            ss.employee,
            e.employee_name,
            e.bank_name,
            e.bank_ac_no,
            ss.net_pay,
            ss.start_date,
            ss.end_date
        from `tabSalary Slip` ss
        join tabEmployee e on e.name = ss.employee
        where ss.payroll_entry = %s
          and ss.docstatus = 1
        order by e.employee_name
    """, (payroll_entry,), as_dict=True)
    return rows


def fetch_bank_codes() -> dict[str, str]:
    return {b["name"]: b["nibss_code"]
            for b in frappe.get_all("Bank", fields=["name", "nibss_code"])
            if b.get("nibss_code")}


def short_narration(start_date, end_date) -> str:
    """Build narration (Fidelity wants 5-47 chars)."""
    if start_date:
        month_year = frappe.utils.formatdate(start_date, "MMM yyyy").upper()
    else:
        month_year = "PAYROLL"
    n = f"PAYMENT OF {month_year} SALARY"
    return n[:47]


def generate_stanbic(rows: list[dict], bank_codes: dict[str, str], out: Path) -> tuple[int, list[str]]:
    headers = ["Reciever Name", "Reciever Account No", "Amount", "Sender",
               "Narration", "Receiever's Narration", "BankCode"]
    skipped = []
    written = 0
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(headers)
        for r in rows:
            bank = (r.get("bank_name") or "").strip()
            acct = (r.get("bank_ac_no") or "").strip()
            net = r.get("net_pay") or 0
            if not bank or not acct or net <= 0:
                skipped.append(f"{r['employee']} ({r['employee_name']}) -- missing bank/account/zero net")
                continue
            code = bank_codes.get(bank)
            if not code:
                skipped.append(f"{r['employee']} ({r['employee_name']}) -- bank `{bank}` has no NIBSS code")
                continue
            narration = short_narration(r.get("start_date"), r.get("end_date"))
            w.writerow([
                r["employee_name"],
                f"#{acct}",       # Stanbic template uses leading #
                round(float(net), 2),
                SENDER_NAME,
                narration,
                narration,
                bank,             # Stanbic template uses bank name (not code) in BankCode col
            ])
            written += 1
    return written, skipped


def generate_fidelity(rows: list[dict], bank_codes: dict[str, str], out: Path) -> tuple[int, list[str]]:
    headers = ["Beneficiary Bank Code", "Beneficiary Account Number ",
               "Beneficiary Name", "Amount",
               "Narration(Must be between 5 to 47 Characters)"]
    skipped = []
    written = 0
    with out.open("w", newline="", encoding="utf-8") as f:
        # Fidelity expects double-quoted fields
        w = csv.writer(f, quoting=csv.QUOTE_ALL)
        w.writerow(headers)
        for r in rows:
            bank = (r.get("bank_name") or "").strip()
            acct = (r.get("bank_ac_no") or "").strip()
            net = r.get("net_pay") or 0
            if not bank or not acct or net <= 0:
                skipped.append(f"{r['employee']} ({r['employee_name']}) -- missing bank/account/zero net")
                continue
            code = bank_codes.get(bank)
            if not code:
                skipped.append(f"{r['employee']} ({r['employee_name']}) -- bank `{bank}` has no NIBSS code")
                continue
            narration = short_narration(r.get("start_date"), r.get("end_date"))
            if len(narration) < 5:
                narration = "PAYROLL"
            # Fidelity: amount with 3 decimal places (matches sample)
            w.writerow([code, acct, r["employee_name"], f"{float(net):.3f}", narration])
            written += 1
    return written, skipped


def main():
    print("=" * 72)
    print(f" Phase 6 / Step 6b -- Bank Upload Generator ({BANK})")
    print(f" Payroll Entry: {PAYROLL_ENTRY}")
    print("=" * 72)

    if PAYROLL_ENTRY == "REPLACE_WITH_PAYROLL_ENTRY_NAME":
        print("  ! Edit PAYROLL_ENTRY at top of script first")
        return
    if not frappe.db.exists("Payroll Entry", PAYROLL_ENTRY):
        print(f"  ! Payroll Entry {PAYROLL_ENTRY!r} not found")
        return

    bank_choice = BANK.upper()
    if bank_choice not in {"STANBIC", "FIDELITY"}:
        print(f"  ! BANK must be STANBIC or FIDELITY, got {BANK!r}")
        return

    rows = fetch_slip_rows(PAYROLL_ENTRY)
    if not rows:
        print(f"  ! No submitted Salary Slips for {PAYROLL_ENTRY}")
        return

    bank_codes = fetch_bank_codes()
    print(f"  Found {len(rows)} Salary Slip(s) | {len(bank_codes)} banks have NIBSS codes")

    out_path = Path(f"/tmp/bank_upload_{bank_choice.lower()}_{PAYROLL_ENTRY}.csv")
    if bank_choice == "STANBIC":
        written, skipped = generate_stanbic(rows, bank_codes, out_path)
    else:
        written, skipped = generate_fidelity(rows, bank_codes, out_path)

    print()
    print(f"  Wrote: {out_path}")
    print(f"  Rows written: {written}")
    print(f"  Skipped:      {len(skipped)}")
    if skipped:
        print()
        print("  Skipped employees (data needs HR fix-up):")
        for s in skipped[:50]:
            print(f"    - {s}")

    # Also expose via Frappe File for browser download
    try:
        with out_path.open("rb") as f:
            content = f.read()
        import base64
        file_doc = frappe.get_doc({
            "doctype": "File",
            "file_name": out_path.name,
            "is_private": 1,   # payroll data: PRIVATE
            "content": base64.b64encode(content).decode(),
            "decode": True,
        }).insert(ignore_permissions=True)
        frappe.db.commit()
        print()
        print("  Download (login required, HR/Finance only):")
        print(f"  https://{frappe.local.site}{file_doc.file_url}")
    except Exception as e:
        print(f"  ! Could not register File doc: {e}")
        print(f"  Read manually from: {out_path}")


try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
