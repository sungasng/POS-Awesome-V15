"""
p57 / Step 12 -- Find the existing draft Journal Entry for the Pedro/Ikeja
NGN 228,000 misposting correction.

Read-only. Lists candidate draft JEs that touch Pedro or Ikeja POS Incoming
accounts in May 2026.
"""
from __future__ import annotations
from pathlib import Path
import frappe

COMPANY = "SUNGAS COMPANY LIMITED"
TARGET_AMOUNT = 228000.0


def main():
    L = []
    p = L.append
    p("# p57 / Step 12 -- Discover draft JE for Pedro/Ikeja NGN 228k correction")
    p("")

    # 1. All draft JEs in the company
    drafts = frappe.db.sql("""
        select name, posting_date, total_debit, user_remark, voucher_type
        from `tabJournal Entry`
        where company = %s and docstatus = 0
        order by posting_date desc, name desc
        limit 50
    """, (COMPANY,), as_dict=True)
    p(f"## All draft Journal Entries (last 50): {len(drafts)}")
    if not drafts:
        p("- (no drafts)")
    else:
        p("| JE | Date | Type | Total Debit (NGN) | Remark (first 80 chars) |")
        p("|----|------|------|-------------------|-------------------------|")
        for d in drafts:
            remark = (d['user_remark'] or '')[:80].replace('\n', ' ')
            p(f"| `{d['name']}` | {d['posting_date']} | {d['voucher_type']} | "
              f"{d['total_debit']:,.2f} | {remark} |")
    p("")

    # 2. Filter to those touching Pedro OR Ikeja POS Incoming accounts
    p("## Candidates touching Pedro or Ikeja POS Incoming accounts")
    candidates = frappe.db.sql("""
        select distinct je.name, je.posting_date, je.total_debit, je.user_remark
        from `tabJournal Entry` je
        join `tabJournal Entry Account` jea on jea.parent = je.name
        where je.company = %s and je.docstatus = 0
          and (jea.account like '%%POS Incoming%%Pedro%%'
               or jea.account like '%%POS Incoming%%Ikeja%%'
               or jea.account like '%%1503%%Pedro%%'
               or jea.account like '%%1503%%Ikeja%%')
        order by je.posting_date desc
    """, (COMPANY,), as_dict=True)
    if not candidates:
        p("- (none)")
    else:
        for c in candidates:
            p(f"### `{c['name']}` -- {c['posting_date']} -- NGN {c['total_debit']:,.2f}")
            p(f"- Remark: {(c['user_remark'] or '')[:200]}")
            rows = frappe.db.sql("""
                select account, debit_in_account_currency as dr, credit_in_account_currency as cr
                from `tabJournal Entry Account`
                where parent = %s
                order by idx
            """, (c['name'],), as_dict=True)
            p("")
            p("| Account | Debit | Credit |")
            p("|---------|-------|--------|")
            for r in rows:
                p(f"| `{r['account']}` | {r['dr']:,.2f} | {r['cr']:,.2f} |")
            p("")

    # 3. Drafts at exactly NGN 228,000
    p("## Drafts at exactly NGN 228,000")
    exact = frappe.db.sql("""
        select name, posting_date, user_remark
        from `tabJournal Entry`
        where company = %s and docstatus = 0
          and abs(total_debit - %s) < 0.01
        order by posting_date desc
    """, (COMPANY, TARGET_AMOUNT), as_dict=True)
    if not exact:
        p("- (none)")
    else:
        for e in exact:
            p(f"- `{e['name']}` ({e['posting_date']}): {(e['user_remark'] or '')[:120]}")
    p("")

    # 4. Recommendation
    p("## Recommendation")
    p("")
    if exact:
        p(f"Submit candidate `{exact[0]['name']}` if its rows match the expected")
        p("flow (debit Pedro POS Incoming, credit Ikeja POS Incoming). To submit:")
        p("```")
        p(f"je = frappe.get_doc('Journal Entry', '{exact[0]['name']}')")
        p("je.submit()")
        p("frappe.db.commit()")
        p("```")
    elif candidates:
        p("Review candidate(s) above. If one matches the intent, submit via:")
        p("```")
        p("je = frappe.get_doc('Journal Entry', '<JE-NAME>')")
        p("je.submit()")
        p("frappe.db.commit()")
        p("```")
    else:
        p(":x: No draft JE found for the Pedro->Ikeja NGN 228,000 correction.")
        p("Ask the agent to write a fresh JE creation+submission script.")
    p("")

    out = "\n".join(L)
    Path("/tmp/p57_step12_je_discover.log").write_text(out, encoding="utf-8")
    print(out)
    print()
    print("  Log: /tmp/p57_step12_je_discover.log")


main()
