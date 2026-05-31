"""
p57: Mode-of-Payment routing audit (data-driven).

Two views:
  A. Mode of Payment default accounts (per company) -- the *source* of routing
  B. Actual historical posting per POS Profile -- what *really* happened to
     receipts at each outlet over the period.

This explains WHY Ikeja's POS receipts went to Pedro's GL: it's almost
certainly because the Mode of Payment `POS` default account for SUNGAS
COMPANY LIMITED was set to a Pedro account.

Read-only diagnostic. Companion script `p57_mop_company_account_fix.py`
(next) will let you reset it to a neutral account, and we'll then
introduce per-profile overrides if the version supports it.
"""
from __future__ import annotations
from pathlib import Path
from datetime import date
import frappe


def main():
    L = []
    p = L.append
    p("# p57 -- Mode-of-Payment routing audit"); p("")

    # A. MOP-level defaults
    p("## A. Mode of Payment company-level default accounts")
    mops = frappe.db.sql("""
        select name, type, enabled from `tabMode of Payment`
        where enabled = 1 order by name
    """, as_dict=True)
    p(f"- Active Mode of Payment records: **{len(mops)}**")
    p("")
    for m in mops:
        accs = frappe.db.sql("""
            select company, default_account
            from `tabMode of Payment Account`
            where parent = %s order by company
        """, (m["name"],), as_dict=True)
        p(f"### `{m['name']}` (type={m['type']})")
        if not accs:
            p("- (no per-company default account set)")
        else:
            p("| Company | Default account |")
            p("|---------|-----------------|")
            for a in accs:
                p(f"| {a['company']} | {a['default_account']} |")
        p("")

    # B. Actual postings per profile (last 12 months)
    p("## B. Actual GL accounts used per POS Profile (last 12 months)")
    p("Looks at submitted POS Invoices and which account each Sales Invoice Payment")
    p("row recorded. This shows what really hit the GL, profile by profile.")
    p("")
    profiles = frappe.db.sql("""
        select name, warehouse from `tabPOS Profile` where disabled = 0
        order by name
    """, as_dict=True)
    for pp in profiles:
        rows = frappe.db.sql("""
            select sip.mode_of_payment, sip.account, sum(sip.amount) as total,
                   count(distinct pi.name) as inv_count
            from `tabSales Invoice Payment` sip
            join `tabPOS Invoice` pi on pi.name = sip.parent
            where pi.pos_profile = %s and pi.docstatus = 1
              and pi.posting_date >= %s
            group by sip.mode_of_payment, sip.account
            order by sip.mode_of_payment
        """, (pp["name"], frappe.utils.add_days(date.today(), -365)), as_dict=True)
        if not rows:
            continue
        # Find expected branch token from warehouse
        wh = pp["warehouse"] or ""
        expected_branch = wh.rsplit(" - ", 1)[0].strip() if " - " in wh else wh
        p(f"### `{pp['name']}` (warehouse `{wh}`, expected branch `{expected_branch}`)")
        p("| Mode | Account | NGN | Invoices | Branch in account | Match |")
        p("|------|---------|-----|----------|-------------------|-------|")
        for r in rows:
            acc = r["account"] or ""
            parts = [x.strip() for x in acc.split(" - ")]
            acct_branch = parts[-2] if len(parts) >= 3 else "?"
            match = ":white_check_mark:" if acct_branch.lower() == (expected_branch or "").lower() else ":x:"
            p(f"| {r['mode_of_payment']} | {acc} | {float(r['total']):,.2f} | "
              f"{r['inv_count']} | {acct_branch} | {match} |")
        p("")

    # C. Mismatched-branch totals (quantified impact)
    p("## C. Total receipts posted to wrong-branch accounts")
    rows = frappe.db.sql("""
        select pi.pos_profile, sip.mode_of_payment, sip.account, sum(sip.amount) as total,
               count(distinct pi.name) as inv_count
        from `tabSales Invoice Payment` sip
        join `tabPOS Invoice` pi on pi.name = sip.parent
        where pi.docstatus = 1
        group by pi.pos_profile, sip.mode_of_payment, sip.account
    """, as_dict=True)
    misposted = []
    for r in rows:
        prof = r["pos_profile"]
        wh = frappe.db.get_value("POS Profile", prof, "warehouse") or ""
        expected_branch = wh.rsplit(" - ", 1)[0].strip() if " - " in wh else wh
        acc = r["account"] or ""
        parts = [x.strip() for x in acc.split(" - ")]
        acct_branch = parts[-2] if len(parts) >= 3 else ""
        if expected_branch and acct_branch and expected_branch.lower() != acct_branch.lower():
            misposted.append({**r, "expected": expected_branch, "actual": acct_branch})
    if not misposted:
        p("- (none -- everything posted to the right branch)")
    else:
        misposted.sort(key=lambda x: -float(x["total"]))
        total_mis = sum(float(r["total"]) for r in misposted)
        p(f"- **Total mis-posted across history: NGN {total_mis:,.2f}** across "
          f"{len(misposted)} (profile, mode, account) combinations.")
        p("")
        p("| POS Profile | Mode | Wrong account (used) | NGN | Invoices | Expected branch |")
        p("|-------------|------|---------------------|-----|----------|-----------------|")
        for r in misposted[:50]:
            p(f"| {r['pos_profile']} | {r['mode_of_payment']} | {r['account']} | "
              f"{float(r['total']):,.2f} | {r['inv_count']} | {r['expected']} |")
        p("")

    p("## Next step (suggested)")
    p("1. Decide the correct per-outlet account convention with HOD Finance:")
    p("   - Single global Mode of Payment defaults (simple but loses per-branch P&L) OR")
    p("   - Per-outlet Mode of Payment records (e.g. `POS - Ikeja`, `POS - Pedro`) and")
    p("     each POS Profile uses its branch's MOP -- cleanest, gives true branch P&L.")
    p("2. Pick one approach. We'll generate a remediation script that:")
    p("   - Creates the per-outlet MOPs (if option 2), OR resets defaults (option 1)")
    p("   - Generates a Journal Entry batch to reverse historic mis-posted receipts")
    p("     from wrong-branch GL to right-branch GL, for HOD Finance approval.")
    p("")

    out = "\n".join(L)
    Path("/tmp/p57_mop_audit.log").write_text(out, encoding="utf-8")
    print(out)
    print()
    print(f"  Log: /tmp/p57_mop_audit.log")


main()
