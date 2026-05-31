"""
p57: Submit MC-COR-YYYYMM-00001 (the NGN 228k Pedro -> Ikeja correction JE).
Idempotent: if already submitted, prints state and exits.
LIVE=1 to actually submit.
"""
from __future__ import annotations
import os
import frappe

JE_NAME = "MC-COR-YYYYMM-00001"


def main():
    live = os.environ.get("LIVE", "0") == "1"
    print(f"# Submit JE `{JE_NAME}` (LIVE={live})")
    print()

    if not frappe.db.exists("Journal Entry", JE_NAME):
        print(f":x: `{JE_NAME}` not found.")
        return

    je = frappe.get_doc("Journal Entry", JE_NAME)
    print(f"- docstatus before: {je.docstatus}")
    print(f"- total_debit: NGN {je.total_debit:,.2f}")
    print(f"- posting_date: {je.posting_date}")
    print(f"- user_remark: {(je.user_remark or '')[:200]}")
    print()
    print("- Rows:")
    for r in je.accounts:
        print(f"    {r.account}  dr={r.debit_in_account_currency:,.2f}  cr={r.credit_in_account_currency:,.2f}")
    print()

    if je.docstatus == 1:
        print(":information_source: already submitted -- nothing to do.")
        return
    if je.docstatus == 2:
        print(":x: cancelled -- cannot resubmit.")
        return

    if not live:
        print("DRY-RUN: re-run with LIVE=1 to submit.")
        return

    try:
        je.submit()
        frappe.db.commit()
        print(f":white_check_mark: submitted -- docstatus now {je.docstatus}")
    except Exception as e:
        print(f":x: submit failed: {e}")


main()
