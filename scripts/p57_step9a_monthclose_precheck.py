"""
Phase 5.7 / Step 9a -- Month-Close Pre-check (read-only).

Lists every condition that would block a clean month-close for a given
month-end date. Run mid-WD+1 to give HOD Finance early visibility on
what the team still owes; re-run on WD+5 to confirm everything is clear
before the lock script is invoked.

Parameters (set as environment variables before invoking):
    MONTH_END   YYYY-MM-DD. Defaults to the last day of the prior month.

Run (replace SHA with the commit you want pinned):
    SHA=<commit>
    export MONTH_END=2026-05-31           # optional
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/$SHA/scripts/p57_step9a_monthclose_precheck.py" -o /tmp/p57pre.py
    bench --site sungasmis.v.frappe.cloud execute "(exec(open('/tmp/p57pre.py').read(), globals()) or (lambda **k: None))"

Output: stdout + /tmp/p57_monthclose_precheck.md
"""

from __future__ import annotations
from pathlib import Path
from datetime import date, timedelta
import calendar
import os
import frappe


def _default_month_end() -> date:
    today = date.today()
    first_of_this_month = today.replace(day=1)
    return first_of_this_month - timedelta(days=1)


def _parse_month_end() -> date:
    raw = os.environ.get("MONTH_END")
    if raw:
        y, m, d = raw.split("-")
        return date(int(y), int(m), int(d))
    return _default_month_end()


def _is_last_day_of_month(d: date) -> bool:
    return d.day == calendar.monthrange(d.year, d.month)[1]


def main() -> None:
    L: list[str] = []
    p = L.append

    month_end = _parse_month_end()
    month_start = month_end.replace(day=1)
    p("# Phase 5.7 / Step 9a -- Month-Close Pre-check")
    p("")
    p(f"- **Target month-end**: `{month_end.isoformat()}`  (last day of month = {_is_last_day_of_month(month_end)})")
    p(f"- **Window scanned**: `{month_start.isoformat()}` -> `{month_end.isoformat()}`")
    p(f"- **Mode**: READ-ONLY -- no records will be modified")
    p("")
    if not _is_last_day_of_month(month_end):
        p("> :warning: MONTH_END is **not** the last day of its month. Most Sungas closes")
        p("> should target the last calendar day. Confirm this is intentional.")
        p("")

    blockers: list[tuple[str, str, str]] = []   # (severity, area, message)
    advisories: list[tuple[str, str, str]] = []

    def block(area: str, msg: str) -> None:
        blockers.append(("BLOCK", area, msg))

    def warn(area: str, msg: str) -> None:
        advisories.append(("WARN", area, msg))

    # ---- 1. Draft POS Invoices in period ----
    pos_drafts = frappe.db.count("POS Invoice",
                                 {"docstatus": 0, "posting_date": ["<=", month_end]})
    p(f"## 1. Draft POS Invoices (posting_date <= {month_end})")
    p(f"- Count: **{pos_drafts}**")
    if pos_drafts:
        block("POS Invoice",
              f"{pos_drafts} draft POS Invoice(s) on or before month-end. "
              f"Run p57_step1c_delete_abandoned.py or submit each manually.")
        rows = frappe.db.sql("""
            select name, posting_date, customer, grand_total, owner
            from `tabPOS Invoice`
            where docstatus = 0 and posting_date <= %s
            order by posting_date desc limit 10
        """, (month_end,), as_dict=True)
        p("  Sample (latest 10):")
        for r in rows:
            p(f"  - {r['name']} | {r['posting_date']} | {r['customer']} | "
              f"NGN {r['grand_total'] or 0:,.2f} | {r['owner']}")
    p("")

    # ---- 2. Draft Sales Invoices in period ----
    si_drafts = frappe.db.count("Sales Invoice",
                                {"docstatus": 0, "posting_date": ["<=", month_end]})
    p(f"## 2. Draft Sales Invoices (posting_date <= {month_end})")
    p(f"- Count: **{si_drafts}**")
    if si_drafts:
        block("Sales Invoice",
              f"{si_drafts} draft Sales Invoice(s) on or before month-end.")
    p("")

    # ---- 3. Draft Purchase Receipts ----
    pr_drafts = frappe.db.count("Purchase Receipt",
                                {"docstatus": 0, "posting_date": ["<=", month_end]})
    p(f"## 3. Draft Purchase Receipts (posting_date <= {month_end})")
    p(f"- Count: **{pr_drafts}**")
    if pr_drafts:
        block("Purchase Receipt",
              f"{pr_drafts} draft Purchase Receipt(s) on or before month-end.")
    p("")

    # ---- 4. Draft Purchase Invoices ----
    pi_drafts = frappe.db.count("Purchase Invoice",
                                {"docstatus": 0, "posting_date": ["<=", month_end]})
    p(f"## 4. Draft Purchase Invoices (posting_date <= {month_end})")
    p(f"- Count: **{pi_drafts}**")
    if pi_drafts:
        block("Purchase Invoice",
              f"{pi_drafts} draft Purchase Invoice(s) on or before month-end.")
    p("")

    # ---- 5. Draft Delivery Notes ----
    dn_drafts = frappe.db.count("Delivery Note",
                                {"docstatus": 0, "posting_date": ["<=", month_end]})
    p(f"## 5. Draft Delivery Notes (posting_date <= {month_end})")
    p(f"- Count: **{dn_drafts}**")
    if dn_drafts:
        block("Delivery Note",
              f"{dn_drafts} draft Delivery Note(s) on or before month-end.")
    p("")

    # ---- 6. Draft Stock Entries ----
    se_drafts = frappe.db.count("Stock Entry",
                                {"docstatus": 0, "posting_date": ["<=", month_end]})
    p(f"## 6. Draft Stock Entries (posting_date <= {month_end})")
    p(f"- Count: **{se_drafts}**")
    if se_drafts:
        block("Stock Entry",
              f"{se_drafts} draft Stock Entry/Entries on or before month-end.")
    p("")

    # ---- 7. POS Closing Shift coverage (POS Awesome) ----
    p("## 7. POS Closing Shift coverage (POS Awesome)")
    active_profiles = frappe.db.sql("""
        select name from `tabPOS Profile` where disabled = 0
    """, as_dict=True)
    profile_names = [r["name"] for r in active_profiles]
    p(f"- Active POS Profiles: **{len(profile_names)}**")

    # Anything that is still an OPEN shift inside the period is a blocker --
    # the shift must be closed before the month can be locked.
    open_shifts = frappe.db.sql("""
        select name, pos_profile, period_start_date, user
        from `tabPOS Opening Shift`
        where docstatus = 1
          and status = 'Open'
          and date(period_start_date) <= %s
        order by period_start_date
    """, (month_end,), as_dict=True)
    if open_shifts:
        block("POS Opening Shift",
              f"{len(open_shifts)} POS Opening Shift(s) still Open with period_start_date <= "
              f"{month_end}. Each must be closed via POS Awesome > Close Shift.")
        p(f"- **{len(open_shifts)} OPEN shift(s) blocking:**")
        for s in open_shifts[:10]:
            p(f"  - {s['name']} | {s['pos_profile']} | start={s['period_start_date']} | user={s['user']}")
    else:
        p("- No open shifts inside the period")

    # Cross-check: every profile that posted POS Invoices in the month should
    # have at least one submitted Closing Shift that covers the period.
    profiles_without_close = []
    for prof in profile_names:
        had_sales = frappe.db.exists("POS Invoice", {
            "pos_profile": prof,
            "docstatus": 1,
            "posting_date": ["between", [month_start, month_end]],
        })
        if not had_sales:
            continue
        n = frappe.db.sql("""
            select count(*) from `tabPOS Closing Shift`
            where pos_profile = %s and docstatus = 1
              and date(period_end_date) between %s and %s
        """, (prof, month_start, month_end))[0][0]
        if n == 0:
            profiles_without_close.append(prof)
    if profiles_without_close:
        block("POS Closing Shift",
              f"{len(profiles_without_close)} active POS Profile(s) had sales in month "
              f"but no submitted Closing Shift with period_end_date in month: "
              + ", ".join(profiles_without_close[:10]))
    elif not open_shifts:
        p("- **PASS** -- every active profile with sales has at least one Closing Shift in the period")
    p("")

    # ---- 8. Repost Item Valuation backlog ----
    p("## 8. Repost Item Valuation backlog")
    rows = frappe.db.sql("""
        select status, count(*) as n
        from `tabRepost Item Valuation`
        where docstatus < 2
        group by status
    """, as_dict=True)
    if not rows:
        p("- **PASS** -- no Repost Item Valuation jobs found")
    else:
        for r in rows:
            p(f"  - {r['status']}: {r['n']}")
        stuck = sum(r["n"] for r in rows
                    if r["status"] in ("Queued", "In Progress", "Failed"))
        if stuck:
            block("Repost Item Valuation",
                  f"{stuck} Repost Item Valuation job(s) still Queued/In Progress/Failed. "
                  f"Wait for queue to drain or escalate to IT.")
    p("")

    # ---- 9. Stock-in-Hand GL vs Stock Ledger tie-out (informational) ----
    p("## 9. Stock-in-Hand GL vs Stock Ledger (informational)")
    try:
        sih_accounts = frappe.db.sql("""
            select name, company
            from `tabAccount`
            where account_type = 'Stock' and is_group = 0 and disabled = 0
        """, as_dict=True)
        if not sih_accounts:
            p("- (No Stock-type accounts found -- skipping)")
        else:
            gl_total = frappe.db.sql("""
                select sum(debit) - sum(credit) as bal
                from `tabGL Entry`
                where account in %s
                  and posting_date <= %s
                  and is_cancelled = 0
            """, ([a["name"] for a in sih_accounts], month_end), as_dict=True)
            gl_bal = float(gl_total[0]["bal"] or 0)
            sle_total = frappe.db.sql("""
                select sum(stock_value_difference) as bal
                from `tabStock Ledger Entry`
                where posting_date <= %s and is_cancelled = 0
            """, (month_end,), as_dict=True)
            sle_bal = float(sle_total[0]["bal"] or 0)
            diff = round(gl_bal - sle_bal, 2)
            p(f"- Stock GL balance @ {month_end}: **NGN {gl_bal:,.2f}**")
            p(f"- Stock Ledger value @ {month_end}: **NGN {sle_bal:,.2f}**")
            p(f"- Difference: **NGN {diff:,.2f}**")
            if abs(diff) >= 1.00:
                warn("SLE vs GL",
                     f"Difference of NGN {diff:,.2f} between Stock-in-Hand GL and Stock "
                     f"Ledger value. Investigate before lock.")
            else:
                p("- **PASS** -- balances tie to within NGN 1.00")
    except Exception as e:
        p(f"- (Skipped -- {e})")
    p("")

    # ---- 10. Existing freeze dates ----
    p("## 10. Current freeze dates")
    cur_stock = frappe.db.get_single_value("Stock Settings", "stock_frozen_upto")
    cur_acc = frappe.db.get_single_value("Accounts Settings", "acc_frozen_upto")
    p(f"- Stock Settings.stock_frozen_upto: `{cur_stock}`")
    p(f"- Accounts Settings.acc_frozen_upto: `{cur_acc}`")
    if cur_stock and cur_stock >= month_end:
        warn("Freeze date",
             f"stock_frozen_upto ({cur_stock}) is already >= target ({month_end}). "
             f"The lock step is a no-op for stock.")
    if cur_acc and cur_acc >= month_end:
        warn("Freeze date",
             f"acc_frozen_upto ({cur_acc}) is already >= target ({month_end}). "
             f"The lock step is a no-op for accounts.")
    p("")

    # ---- Summary ----
    p("---")
    p("")
    p("## Summary")
    p("")
    p(f"- **Blockers**: {len(blockers)}  (must be 0 before lock)")
    p(f"- **Advisories**: {len(advisories)}  (review before lock; do not block)")
    p("")
    if blockers:
        p("### Blockers")
        p("| # | Area | Message |")
        p("|---|------|---------|")
        for i, (_, area, msg) in enumerate(blockers, 1):
            p(f"| {i} | {area} | {msg} |")
        p("")
    if advisories:
        p("### Advisories")
        p("| # | Area | Message |")
        p("|---|------|---------|")
        for i, (_, area, msg) in enumerate(advisories, 1):
            p(f"| {i} | {area} | {msg} |")
        p("")
    if not blockers and not advisories:
        p("**All checks pass.** Period is ready to be locked.")
        p("")
    elif not blockers:
        p("**No blockers.** Review advisories with HOD Finance, then proceed to lock.")
        p("")
    else:
        p("**Cannot lock yet.** Clear blockers above, then re-run this pre-check.")
        p("")

    out = "\n".join(L)
    Path("/tmp/p57_monthclose_precheck.md").write_text(out, encoding="utf-8")
    print(out)
    print()
    print(f"  Full report: /tmp/p57_monthclose_precheck.md")
    print(f"  Blockers={len(blockers)}  Advisories={len(advisories)}")


main()
