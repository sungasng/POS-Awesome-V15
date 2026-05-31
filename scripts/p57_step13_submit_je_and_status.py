"""
p57 / Step 13 -- Submit Pedro/Ikeja correction JE + show repost backlog status.

What it does:
  1. Submits Journal Entry `MC-COR-YYYYMM-00001` (the NGN 228k Pedro -> Ikeja correction).
     Skips if already submitted (idempotent).
  2. Shows the Repost Item Valuation backlog: total count + grouped by status.
     Failed jobs get printed with their error so we can decide whether to retry
     or manually resolve.
  3. Verifies POSA-CS-26-0000001 closing shift status.

Read-only by default for the JE; set LIVE=1 to actually submit.
Repost stats are always read-only.
"""
from __future__ import annotations
from pathlib import Path
import os
import frappe

JE_NAME = "MC-COR-YYYYMM-00001"
CLOSING_SHIFT = "POSA-CS-26-0000001"


def main():
    L = []
    p = L.append
    live = os.environ.get("LIVE", "0") == "1"

    p("# p57 / Step 13 -- Submit JE + check repost backlog")
    p("")
    p(f"- Mode: {'LIVE' if live else 'DRY-RUN'}")
    p("")

    # 1) Closing Shift verification
    p("## 1. Closing Shift verification")
    if frappe.db.exists("POS Closing Shift", CLOSING_SHIFT):
        cs = frappe.db.get_value(
            "POS Closing Shift", CLOSING_SHIFT,
            ["status", "docstatus", "period_start_date", "period_end_date",
             "pos_profile", "pos_opening_shift"],
            as_dict=True,
        )
        p(f"- name: `{CLOSING_SHIFT}`")
        p(f"- docstatus: {cs['docstatus']} (1=submitted)")
        p(f"- status: {cs['status']}")
        p(f"- pos_profile: {cs['pos_profile']}")
        p(f"- period_start_date: {cs['period_start_date']}")
        p(f"- period_end_date: {cs['period_end_date']}")
    else:
        p(f"- :x: `{CLOSING_SHIFT}` not found")
    p("")

    # 2) Journal Entry submission
    p(f"## 2. Journal Entry `{JE_NAME}`")
    if not frappe.db.exists("Journal Entry", JE_NAME):
        p(f"- :x: `{JE_NAME}` not found")
    else:
        je = frappe.get_doc("Journal Entry", JE_NAME)
        p(f"- docstatus: {je.docstatus} (0=draft, 1=submitted)")
        p(f"- total_debit: NGN {je.total_debit:,.2f}")
        p(f"- posting_date: {je.posting_date}")
        if je.docstatus == 0:
            if not live:
                p(f"- DRY-RUN: would submit `{JE_NAME}`")
            else:
                try:
                    je.submit()
                    frappe.db.commit()
                    p(f"- :white_check_mark: submitted `{JE_NAME}` -> new docstatus={je.docstatus}")
                except Exception as e:
                    p(f"- :x: submit failed: {e}")
        else:
            p("- :information_source: already submitted")
    p("")

    # 3) Repost Item Valuation backlog
    p("## 3. Repost Item Valuation backlog")
    rows = frappe.db.sql("""
        select status, count(*) as n
        from `tabRepost Item Valuation`
        group by status
        order by n desc
    """, as_dict=True)
    if not rows:
        p("- :white_check_mark: no Repost Item Valuation records")
    else:
        p("| Status | Count |")
        p("|--------|-------|")
        for r in rows:
            p(f"| {r['status']} | {r['n']} |")
    p("")

    # Detail any failed reposts (most important for unblocking month-close)
    failed = frappe.get_all(
        "Repost Item Valuation",
        filters={"status": "Failed"},
        fields=["name", "voucher_type", "voucher_no", "error_log", "modified"],
        order_by="modified desc",
        limit=10,
    )
    if failed:
        p("### Failed reposts (first 10)")
        for f in failed:
            err = (f.get("error_log") or "")[:300].replace("\n", " ")
            p(f"- `{f['name']}` voucher={f['voucher_type']}/{f['voucher_no']}")
            p(f"  error: {err}")
        p("")

    # Show the queued/in-progress ones too
    qip = frappe.get_all(
        "Repost Item Valuation",
        filters={"status": ["in", ["Queued", "In Progress"]]},
        fields=["name", "status", "voucher_type", "voucher_no", "modified"],
        order_by="modified desc",
        limit=20,
    )
    if qip:
        p("### Queued / In Progress reposts")
        p("| Name | Status | Voucher | Modified |")
        p("|------|--------|---------|----------|")
        for q in qip:
            p(f"| `{q['name']}` | {q['status']} | {q['voucher_type']}/{q['voucher_no']} | "
              f"{q['modified']} |")
        p("")
        p("These usually drain via background workers within minutes. If stuck > 30 min,")
        p("run: `bench --site sungasmis.v.frappe.cloud execute frappe.utils.background_jobs.execute_job` or escalate to IT.")

    out = "\n".join(L)
    Path("/tmp/p57_step13.log").write_text(out, encoding="utf-8")
    print(out)
    print()
    print("  Log: /tmp/p57_step13.log")


main()
