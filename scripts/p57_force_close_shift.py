"""
p57: Programmatically close POSA-OS-26-0000003 (POS Awesome UI silently failed).

What this does
==============
1. Reads the Opening Shift POSA-OS-26-0000003.
2. Reads all 14 submitted POS Invoices linked to it.
3. Computes expected totals per Mode of Payment.
4. Builds a POS Closing Shift doc with closing amounts from env vars
   (defaulting to the expected = matching the expected, zero variance).
5. Validates + submits it.
6. POS Awesome's submit hook will:
   - Create POS Invoice Merge Log
   - Consolidate the 14 POS Invoices into one submitted Sales Invoice
   - Mark all linked POS Invoices as 'Consolidated'
   - Flip POS Opening Shift status to 'Closed'

Parameters (environment variables):
    CASH_CLOSING    Closing amount for Cash mode. Default = expected.
    POS_CLOSING     Closing amount for POS / Card mode. Default = expected.
    DRAFT_CLOSING   Closing amount for Bank Draft. Default = expected.
    LIVE            "1" to actually submit. Default "0" (dry-run).
    POS_REMARKS     Optional comment to add to the Closing Shift.

Run (replace SHA):
    SHA=<commit>
    export CASH_CLOSING=430480
    export POS_CLOSING=228000
    export DRAFT_CLOSING=0
    export POS_REMARKS='Cash variance NGN 5,000 short -- banked 19-May-2026, signed by Plant Manager.'
    cd ~/frappe-bench
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/$SHA/scripts/p57_force_close_shift.py" -o /tmp/p57c.py
    # 1) DRY-RUN
    bench --site sungasmis.v.frappe.cloud execute "(exec(open('/tmp/p57c.py').read(), globals()) or (lambda **k: None))"
    # 2) LIVE
    export LIVE=1
    bench --site sungasmis.v.frappe.cloud execute "(exec(open('/tmp/p57c.py').read(), globals()) or (lambda **k: None))"
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime
import os
import frappe

SHIFT = "POSA-OS-26-0000003"


def _env_float(name: str, default: float | None = None) -> float | None:
    v = os.environ.get(name)
    if v is None or v == "":
        return default
    return float(str(v).replace(",", ""))


def main():
    L = []
    p = L.append
    live = os.environ.get("LIVE", "0") == "1"
    remarks = os.environ.get("POS_REMARKS", "")

    p(f"# p57 -- Force-close `{SHIFT}` programmatically")
    p("")
    p(f"- Mode: {'LIVE (will submit)' if live else 'DRY-RUN (no writes)'}")
    p(f"- Run as: `{frappe.session.user}` at `{datetime.utcnow().isoformat()}Z`")
    p("")

    if not frappe.db.exists("POS Opening Shift", SHIFT):
        p(f"**ABORT** -- {SHIFT} does not exist."); _save(L); return
    os_doc = frappe.get_doc("POS Opening Shift", SHIFT)
    if os_doc.docstatus != 1:
        p(f"**ABORT** -- Opening Shift docstatus = {os_doc.docstatus} (expected 1)."); _save(L); return
    if os_doc.status != "Open":
        p(f"**ABORT** -- Opening Shift status = {os_doc.status} (expected 'Open')."); _save(L); return

    p("## Opening Shift")
    p(f"- POS Profile: {os_doc.pos_profile}")
    p(f"- Cashier: {os_doc.user}")
    p(f"- Period start: {os_doc.period_start_date}")
    p(f"- Company: {os_doc.company}")
    p("")

    # Find linked POS Invoices via the POS Awesome custom field
    field = "posa_pos_opening_shift"
    try:
        frappe.db.sql(f"select 1 from `tabPOS Invoice` where {field} = %s limit 1", (SHIFT,))
    except Exception:
        field = "pos_opening_shift"
    pos_invoices = frappe.db.sql(f"""
        select name, posting_date, customer, grand_total, status, docstatus
        from `tabPOS Invoice`
        where {field} = %s and docstatus = 1
        order by posting_date
    """, (SHIFT,), as_dict=True)

    p(f"## Linked POS Invoices (link field = `{field}`)")
    p(f"- Count: **{len(pos_invoices)}**")
    if not pos_invoices:
        p("**ABORT** -- no submitted POS Invoices linked to this shift, cannot close."); _save(L); return
    total_grand = sum(float(r["grand_total"] or 0) for r in pos_invoices)
    p(f"- Total grand_total: **NGN {total_grand:,.2f}**")
    for inv in pos_invoices:
        p(f"  - {inv['name']} | {inv['posting_date']} | {inv['customer']} | "
          f"NGN {float(inv['grand_total'] or 0):,.2f} | status={inv['status']}")
    p("")

    # Aggregate payments per mode of payment, per company-account
    payments_agg = frappe.db.sql(f"""
        select sip.mode_of_payment, sip.account, sum(sip.amount) as amt
        from `tabSales Invoice Payment` sip
        join `tabPOS Invoice` pi on pi.name = sip.parent
        where pi.{field} = %s and pi.docstatus = 1
        group by sip.mode_of_payment, sip.account
        order by sip.mode_of_payment
    """, (SHIFT,), as_dict=True)
    p("## Expected payments by mode (from submitted POS Invoices)")
    p("| Mode of Payment | Account | Expected NGN |")
    p("|-----------------|---------|--------------|")
    for r in payments_agg:
        p(f"| {r['mode_of_payment']} | {r['account']} | {float(r['amt'] or 0):,.2f} |")
    p("")

    # Per-mode closing amount inputs (case-insensitive matching on mode name)
    def _closing_for(mode: str, expected: float) -> float:
        m = mode.lower()
        if "cash" in m:
            return _env_float("CASH_CLOSING", expected) or expected
        if "draft" in m or "cheque" in m:
            return _env_float("DRAFT_CLOSING", expected) or expected
        # everything else (Card/POS/Transfer/etc) -> POS_CLOSING bucket if user set it
        return _env_float("POS_CLOSING", expected) or expected

    # Pull POS Profile defaults for required child tables
    pp = frappe.get_doc("POS Profile", os_doc.pos_profile)

    # Determine taxes total from invoices for the Closing Shift taxes table
    taxes_agg = frappe.db.sql(f"""
        select tax.account_head, sum(tax.tax_amount) as amt, tax.rate
        from `tabSales Taxes and Charges` tax
        join `tabPOS Invoice` pi on pi.name = tax.parent
        where pi.{field} = %s and pi.docstatus = 1
        group by tax.account_head, tax.rate
    """, (SHIFT,), as_dict=True)

    # Build the Closing Shift draft
    p("## Building POS Closing Shift")
    cs = frappe.new_doc("POS Closing Shift")
    cs.pos_opening_shift = SHIFT
    cs.period_start_date = os_doc.period_start_date
    cs.period_end_date = frappe.utils.now_datetime()
    cs.posting_date = frappe.utils.today()
    cs.posting_time = frappe.utils.nowtime()
    cs.pos_profile = os_doc.pos_profile
    cs.company = os_doc.company
    cs.user = os_doc.user
    cs.grand_total = total_grand
    cs.net_total = total_grand - sum(float(t["amt"] or 0) for t in taxes_agg)
    qty_rows = frappe.db.sql(f"""
        select coalesce(sum(pii.qty), 0)
        from `tabPOS Invoice Item` pii
        join `tabPOS Invoice` pi on pi.name = pii.parent
        where pi.{field} = %s and pi.docstatus = 1
    """, (SHIFT,))
    cs.total_quantity = float(qty_rows[0][0]) if qty_rows and qty_rows[0] else 0.0

    # Payment Reconciliation table
    cs.payment_reconciliation = []
    for r in payments_agg:
        expected = float(r["amt"] or 0)
        closing = _closing_for(r["mode_of_payment"], expected)
        cs.append("payment_reconciliation", {
            "mode_of_payment": r["mode_of_payment"],
            "opening_amount": 0,
            "expected_amount": expected,
            "closing_amount": closing,
            "difference": closing - expected,
        })
        p(f"- {r['mode_of_payment']}: expected NGN {expected:,.2f}, "
          f"closing NGN {closing:,.2f}, diff NGN {closing - expected:,.2f}")

    # Taxes table
    cs.taxes = []
    for t in taxes_agg:
        cs.append("taxes", {
            "account_head": t["account_head"],
            "amount": float(t["amt"] or 0),
            "rate": float(t["rate"] or 0),
        })

    # Linked POS Invoices table
    cs.pos_transactions = []
    for inv in pos_invoices:
        cs.append("pos_transactions", {
            "pos_invoice": inv["name"],
            "posting_date": inv["posting_date"],
            "grand_total": float(inv["grand_total"] or 0),
            "customer": inv["customer"],
        })

    p("")
    p(f"- Built doc in-memory. Total invoices: {len(cs.pos_transactions)}. "
      f"Total grand: NGN {cs.grand_total:,.2f}. "
      f"Payment recon rows: {len(cs.payment_reconciliation)}. "
      f"Taxes: {len(cs.taxes)}.")
    p("")

    if not live:
        p("## DRY-RUN -- not saving.")
        p("Re-run with `LIVE=1` to actually submit.")
        _save(L); return

    # ---- LIVE ----
    p("## Applying")
    try:
        cs.insert(ignore_permissions=True)
        p(f"- :white_check_mark: inserted draft `{cs.name}`")
        cs.submit()
        p(f"- :white_check_mark: submitted `{cs.name}`")
        if remarks:
            cs.add_comment("Comment", remarks)
            p(f"- :white_check_mark: added remark comment")
        frappe.db.commit()
    except Exception as e:
        frappe.db.rollback()
        p(f"- :x: FAILED: {type(e).__name__}: {e}")
        import traceback
        p("```")
        p(traceback.format_exc())
        p("```")
        _save(L); return

    # Verify the Opening Shift is now Closed
    os_doc.reload()
    p("")
    p("## Verification")
    p(f"- Opening Shift status after close: **{os_doc.status}**")
    cs.reload()
    p(f"- Closing Shift: {cs.name} docstatus={cs.docstatus}")

    # Show consolidation result
    pim = frappe.db.sql("""
        select name, docstatus, consolidated_invoice
        from `tabPOS Invoice Merge Log`
        order by creation desc limit 3
    """, as_dict=True)
    p("- Recent POS Invoice Merge Logs:")
    for r in pim:
        p(f"  - {r['name']} | docstatus={r['docstatus']} | "
          f"consolidated_invoice={r['consolidated_invoice']}")

    _save(L)


def _save(L):
    out = "\n".join(L)
    Path("/tmp/p57_force_close.log").write_text(out, encoding="utf-8")
    print(out)
    print()
    print(f"  Log: /tmp/p57_force_close.log")


main()
