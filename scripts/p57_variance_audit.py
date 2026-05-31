"""
p57: Audit today's POS Closing Shifts -- variance trail.

Shows every Closing Shift submitted today (across all outlets):
  - expected vs closing amount per MoP
  - difference per MoP
  - which GL account caught the variance (write-off / difference account)
  - cashier + approver
  - the consolidated Sales Invoice + JE that resulted
  - any remarks / comments

Read-only.
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime, date
import frappe

COMPANY = "SUNGAS COMPANY LIMITED"


def main():
    L = []
    p = L.append
    today = date.today()
    p("# p57: Today's POS Closing Shift variance audit")
    p("")
    p(f"- Date: `{today}`")
    p(f"- Run at: `{datetime.utcnow().isoformat()}Z`")
    p("")

    rows = frappe.db.sql("""
        select name, pos_profile, user, period_start_date, period_end_date,
               grand_total, posting_date, modified, modified_by, docstatus, status,
               pos_opening_shift
        from `tabPOS Closing Shift`
        where date(period_end_date) = %s
        order by period_end_date desc
    """, (today,), as_dict=True)

    if not rows:
        p("- (no Closing Shifts submitted today)")
        _save(L)
        return

    p(f"## {len(rows)} Closing Shift(s) today")
    p("")

    total_variance = 0.0
    for cs in rows:
        p(f"### `{cs['name']}` -- {cs['pos_profile']}")
        p(f"- cashier: `{cs['user']}`")
        p(f"- submitted by: `{cs['modified_by']}` at `{cs['modified']}`")
        p(f"- period: {cs['period_start_date']} -> {cs['period_end_date']}")
        p(f"- grand_total: NGN {cs['grand_total'] or 0:,.2f}")
        p(f"- opening shift: `{cs['pos_opening_shift']}`")
        p(f"- docstatus: {cs['docstatus']} / status: {cs['status']}")
        p("")

        recon = frappe.db.sql("""
            select mode_of_payment, expected_amount, closing_amount, difference
            from `tabPOS Closing Shift Detail`
            where parent = %s
            order by mode_of_payment
        """, (cs['name'],), as_dict=True)
        if recon:
            p("| MoP | Expected | Closing | Difference |")
            p("|-----|---------:|--------:|-----------:|")
            cs_variance = 0
            for r in recon:
                diff = (r['closing_amount'] or 0) - (r['expected_amount'] or 0)
                cs_variance += diff
                flag = ""
                if abs(diff) >= 100000:
                    flag = " :rotating_light:"
                elif abs(diff) >= 10000:
                    flag = " :warning:"
                p(f"| {r['mode_of_payment']} | {r['expected_amount'] or 0:,.2f} | "
                  f"{r['closing_amount'] or 0:,.2f} | {diff:+,.2f}{flag} |")
            p(f"\n**Shift total variance: NGN {cs_variance:+,.2f}**")
            total_variance += cs_variance
        else:
            p("- (no payment reconciliation rows)")
        p("")

        # Linked consolidated Sales Invoice + JE
        consol = frappe.db.sql("""
            select pim.name as merge_log, pim.consolidated_invoice, pim.docstatus
            from `tabPOS Invoice Merge Log` pim
            where pim.pos_closing_entry = %s
        """, (cs['name'],), as_dict=True)
        if consol:
            for c in consol:
                p(f"- Merge Log: `{c['merge_log']}` -> Sales Invoice `{c['consolidated_invoice']}`")

        # Comments on the Closing Shift
        comments = frappe.db.sql("""
            select owner, creation, content from `tabComment`
            where reference_doctype = 'POS Closing Shift' and reference_name = %s
            order by creation
        """, (cs['name'],), as_dict=True)
        if comments:
            p("- Comments:")
            for c in comments:
                content = (c['content'] or '').replace("\n", " ")[:200]
                p(f"  - {c['creation']} by `{c['owner']}`: {content}")
        p("")
        p("---")
        p("")

    p(f"## TOTAL variance across all shifts today: **NGN {total_variance:+,.2f}**")
    p("")

    # Where did the variance go? Find GL entries on the difference account.
    p("## GL impact -- entries on POS Profile write_off / difference account today")
    diff_accounts = frappe.db.sql("""
        select distinct write_off_account
        from `tabPOS Profile`
        where company = %s and disabled = 0 and write_off_account is not null
    """, (COMPANY,), as_dict=True)
    p(f"- Difference accounts in use across POS Profiles: "
      f"{', '.join(set(filter(None, [r['write_off_account'] for r in diff_accounts])))}")
    p("")
    for acc_row in diff_accounts:
        acc = acc_row.get('write_off_account')
        if not acc:
            continue
        gles = frappe.db.sql("""
            select posting_date, voucher_type, voucher_no, debit, credit, remarks
            from `tabGL Entry`
            where account = %s and posting_date = %s
              and company = %s and is_cancelled = 0
            order by creation
        """, (acc, today, COMPANY), as_dict=True)
        if not gles:
            continue
        p(f"### `{acc}` -- {len(gles)} GL entry today")
        p("| Voucher | Dr | Cr | Remarks |")
        p("|---------|----|----|---------|")
        for g in gles:
            rem = (g['remarks'] or '').replace("\n", " ")[:120]
            p(f"| {g['voucher_type']}/{g['voucher_no']} | {g['debit'] or 0:,.2f} | "
              f"{g['credit'] or 0:,.2f} | {rem} |")
        p("")

    _save(L)


def _save(L):
    out = "\n".join(L)
    Path("/tmp/p57_variance_audit.log").write_text(out, encoding="utf-8")
    print(out)
    print()
    print("  Log: /tmp/p57_variance_audit.log")


main()
