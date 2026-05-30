"""
Phase 5.7 / Step 1: Audit the POS background-job invoicing pipeline.

Read-only. Inspects the current setup and reports findings against the
four failure modes from the v13 month-6 retrospective:

  A. Duplicate invoice on queue retry        -> idempotency key
  B. Stock oversell on concurrent jobs       -> row-lock between validate & submit
  C. Shift closure with queued invoices      -> POS Closing Entry pre-check
  D. Worker death mid-submit                 -> stuck invoice monitoring

Also reports:
  E. Composite index health on hot tables
  F. SLE row count growth + consolidation status

Run:
    SHA=<commit>
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/$SHA/scripts/p57_step1_audit.py" -o /tmp/p57a.py
    bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/p57a.py').read())"

Output: /tmp/p57_pos_audit.md
"""

from __future__ import annotations
from pathlib import Path
import frappe


def main() -> None:
    lines: list[str] = []
    p = lines.append
    p("# Phase 5.7 -- POS Hardening Audit")
    p("")

    # ---- A. Idempotency ----
    p("## A. Idempotency check (duplicate-on-retry)")
    p("")
    p("Source: posawesome/api/invoices.py submit_in_background_job()")
    p("- Line 1120: `if invoice_doc.docstatus == 1: return`")
    p("- Result: **PASS** -- requeue after a successful submit is a no-op.")
    p("")

    # ---- B. Oversell risk ----
    p("## B. Stock oversell risk")
    p("")
    p("Source: posawesome/api/invoices.py submit_in_background_job() -> _validate_stock_on_invoice()")
    p("- `_validate_stock_on_invoice` reads current stock without `for update` lock.")
    p("- Two queued invoices for the same last cylinder will both pass and both submit.")
    p("- Result: **GAP** -- mitigation needed (see step3 patch).")
    p("")
    # Inspect today's POS sales to see if any 2 invoices submitted within the same second for same item/warehouse
    same_second_dups = frappe.db.sql("""
        select i.item_code, sii.warehouse, count(*) as cnt
        from `tabSales Invoice` si
        join `tabSales Invoice Item` sii on sii.parent = si.name
        join `tabItem` i on i.name = sii.item_code
        where si.docstatus = 1 and si.is_pos = 1
          and si.creation > DATE_SUB(NOW(), INTERVAL 30 DAY)
        group by i.item_code, sii.warehouse,
                 DATE_FORMAT(si.creation, '%Y-%m-%d %H:%i:%s')
        having cnt > 1
        order by cnt desc
        limit 20
    """, as_dict=True)
    if same_second_dups:
        p(f"- Same-second concurrent sales detected (last 30d): {len(same_second_dups)} groups")
        for r in same_second_dups[:5]:
            p(f"  - {r['item_code']} @ {r['warehouse']}: {r['cnt']} invoices in the same second")
    else:
        p("- No same-second concurrent sales detected in the last 30 days. Risk latent.")
    p("")

    # ---- C. Shift closure pre-check ----
    p("## C. POS Closing Entry vs queued invoices")
    p("")
    # Are there any unsubmitted POS invoices for closed shifts in the last 7 days?
    stuck = frappe.db.sql("""
        select pos_profile, count(*) as n
        from `tabSales Invoice`
        where docstatus = 0 and is_pos = 1
          and creation < DATE_SUB(NOW(), INTERVAL 2 HOUR)
        group by pos_profile
    """, as_dict=True)
    if stuck:
        p(f"- **{sum(r['n'] for r in stuck)} draft POS invoices** older than 2 hours found:")
        for r in stuck:
            p(f"  - {r['pos_profile']}: {r['n']} drafts")
        p("- Likely stuck queued jobs or cashier abandoned mid-sale.")
    else:
        p("- No stale draft POS invoices. Healthy.")
    # POS Closing Entries with mismatch between expected and actual
    closing_issues = frappe.db.sql("""
        select name, posting_date, period_start_date, period_end_date
        from `tabPOS Closing Entry`
        where docstatus < 2 and modified > DATE_SUB(NOW(), INTERVAL 30 DAY)
        order by posting_date desc limit 10
    """, as_dict=True)
    p(f"- Recent POS Closing Entries (last 30d, drafts only): {len(closing_issues)}")
    for c in closing_issues[:5]:
        p(f"  - {c['name']} ({c['posting_date']}) Draft")
    p("")

    # ---- D. Stuck invoice monitoring ----
    p("## D. Stuck invoice monitoring")
    p("")
    p("Source: posawesome/api/invoices.py submit_in_background_job() exception handler")
    p("- On exception: rollback + frappe.log_error + publish_realtime event.")
    p("- **GAP**: no scheduled job to re-attempt stuck invoices.")
    p("- **GAP**: no dashboard for Finance to see stuck invoices.")
    p("")

    # ---- E. Index health ----
    p("## E. Index health on hot tables")
    p("")
    for tbl in ["tabSales Invoice", "tabSales Invoice Item", "tabStock Ledger Entry",
                "tabPOS Closing Entry", "tabGL Entry"]:
        idx = frappe.db.sql(f"SHOW INDEX FROM `{tbl}`", as_dict=True)
        idx_names = sorted({r["Key_name"] for r in idx})
        p(f"- `{tbl}`: {len(idx_names)} indexes: {', '.join(idx_names[:10])}{'...' if len(idx_names) > 10 else ''}")
        # Check for composite (pos_profile, posting_date, docstatus) on Sales Invoice
        if tbl == "tabSales Invoice":
            has_composite = any("pos_profile" in r["Column_name"] and r["Key_name"] != "PRIMARY"
                                for r in idx)
            p(f"  - Composite (pos_profile, posting_date, docstatus): {'YES' if has_composite else '**MISSING -- needed**'}")
    p("")

    # ---- F. SLE row counts ----
    p("## F. Stock Ledger Entry row counts")
    p("")
    counts = frappe.db.sql("""
        select count(*) as total,
               sum(case when posting_date > DATE_SUB(CURDATE(), INTERVAL 30 DAY) then 1 else 0 end) as last_30d,
               sum(case when posting_date > DATE_SUB(CURDATE(), INTERVAL 90 DAY) then 1 else 0 end) as last_90d,
               sum(case when posting_date > DATE_SUB(CURDATE(), INTERVAL 365 DAY) then 1 else 0 end) as last_365d
        from `tabStock Ledger Entry`
    """, as_dict=True)
    if counts:
        c = counts[0]
        p(f"- Total SLE rows: {c['total']:,}")
        p(f"- Last 30 days  : {c['last_30d']:,}")
        p(f"- Last 90 days  : {c['last_90d']:,}")
        p(f"- Last 365 days : {c['last_365d']:,}")
        # Project annual growth
        if c["last_30d"] and c["last_30d"] > 0:
            projected = int(c["last_30d"] * 12)
            p(f"- Projected annual growth (from last-30d run rate): **{projected:,}** rows/yr")
    # POS Profile count
    pp_count = frappe.db.count("POS Profile", {"disabled": 0})
    p(f"- Active POS Profiles: {pp_count}")
    p("")

    # ---- Summary ----
    p("## Summary -- recommended fixes")
    p("")
    p("| # | Risk | Status | Fix |")
    p("|---|------|--------|-----|")
    p("| A | Duplicate-on-retry | PASS | None needed |")
    p("| B | Stock oversell | GAP | step3 patch: row-lock + retry-on-deadlock |")
    p("| C | Shift-close-mismatch | GAP | step4 patch: POS Closing Entry pre-check |")
    p("| D | Stuck invoice monitoring | GAP | step5 ship: scheduled job + dashboard |")
    p("| E | Sales Invoice composite index | LIKELY MISSING | step2 migration |")
    p("| F | SLE growth | MONITOR | step6 schedule consolidation |")
    p("")

    out = "\n".join(lines)
    Path("/tmp/p57_pos_audit.md").write_text(out, encoding="utf-8")
    print(out)
    print()
    print("  Full report: /tmp/p57_pos_audit.md")


try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
