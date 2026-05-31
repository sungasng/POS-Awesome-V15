"""
Phase 5.7 / Step 9a -- Month-Close Lock script.

Sets:
    Stock Settings.stock_frozen_upto = MONTH_END
    Accounts Settings.acc_frozen_upto = MONTH_END

This is the technical seal on the monthly close. Run ONLY after HOD
Finance and MD have signed the close pack (Annex T-03).

Guards:
    1. Defaults to DRY-RUN: nothing is changed unless LIVE=1 is set.
    2. Refuses to write if the pre-check (same logic as p57_step9a_monthclose_precheck.py)
       reports any blockers, unless FORCE=1 is also set.
    3. Refuses if MONTH_END is in the future or more than 90 days in the past.
    4. Refuses if existing freeze date is already at/after MONTH_END (idempotent).

Parameters (environment variables):
    MONTH_END   YYYY-MM-DD. Defaults to last day of prior month.
    LIVE        "1" to actually write. Default "0" (dry-run).
    FORCE       "1" to ignore blockers. Default "0". USE WITH HOD FINANCE WRITTEN APPROVAL ONLY.

Run (replace SHA):
    SHA=<commit>
    export MONTH_END=2026-05-31
    # 1) DRY-RUN first (no writes)
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/$SHA/scripts/p57_step9a_monthclose_lock.py" -o /tmp/p57lock.py
    bench --site sungasmis.v.frappe.cloud execute "(exec(open('/tmp/p57lock.py').read(), globals()) or (lambda **k: None))"
    # 2) If dry-run looks correct, run LIVE
    export LIVE=1
    bench --site sungasmis.v.frappe.cloud execute "(exec(open('/tmp/p57lock.py').read(), globals()) or (lambda **k: None))"

Output: stdout + /tmp/p57_monthclose_lock.log
"""

from __future__ import annotations
from pathlib import Path
from datetime import date, timedelta, datetime
import calendar
import os
import frappe


def _default_month_end() -> date:
    today = date.today()
    first_of_this_month = today.replace(day=1)
    return first_of_this_month - timedelta(days=1)


def _parse_date(raw: str) -> date:
    y, m, d = raw.split("-")
    return date(int(y), int(m), int(d))


def _is_last_day_of_month(d: date) -> bool:
    return d.day == calendar.monthrange(d.year, d.month)[1]


def _count(doctype: str, filters: dict) -> int:
    return frappe.db.count(doctype, filters)


def _precheck_blockers(month_end: date, month_start: date) -> list[str]:
    """Re-implements the precheck logic; returns list of blocker messages."""
    blockers: list[str] = []
    for doctype in ("POS Invoice", "Sales Invoice", "Purchase Receipt",
                    "Purchase Invoice", "Delivery Note", "Stock Entry"):
        n = _count(doctype, {"docstatus": 0, "posting_date": ["<=", month_end]})
        if n:
            blockers.append(f"{n} draft {doctype}(s) on or before {month_end}")

    # POS Awesome: open shifts in period are blockers
    open_shifts = frappe.db.sql("""
        select name from `tabPOS Opening Shift`
        where docstatus = 1 and status = 'Open'
          and date(period_start_date) <= %s
    """, (month_end,), as_dict=True)
    if open_shifts:
        blockers.append(f"{len(open_shifts)} POS Opening Shift(s) still Open with start <= {month_end}")

    # POS Closing Shift coverage
    profiles = [r["name"] for r in frappe.db.sql(
        "select name from `tabPOS Profile` where disabled = 0", as_dict=True)]
    no_close = []
    for prof in profiles:
        had_sales = frappe.db.exists("POS Invoice", {
            "pos_profile": prof, "docstatus": 1,
            "posting_date": ["between", [month_start, month_end]]})
        if not had_sales:
            continue
        n = frappe.db.sql("""
            select count(*) from `tabPOS Closing Shift`
            where pos_profile = %s and docstatus = 1
              and date(period_end_date) between %s and %s
        """, (prof, month_start, month_end))[0][0]
        if n == 0:
            no_close.append(prof)
    if no_close:
        blockers.append(f"{len(no_close)} POS Profile(s) with sales lack a Closing Shift in month: "
                        + ", ".join(no_close[:5]))

    # Repost queue
    rows = frappe.db.sql("""
        select status, count(*) as n from `tabRepost Item Valuation`
        where docstatus < 2 group by status
    """, as_dict=True)
    stuck = sum(r["n"] for r in rows if r["status"] in ("Queued", "In Progress", "Failed"))
    if stuck:
        blockers.append(f"{stuck} Repost Item Valuation job(s) Queued/In Progress/Failed")

    return blockers


def main() -> None:
    L: list[str] = []
    p = L.append

    raw_me = os.environ.get("MONTH_END")
    month_end = _parse_date(raw_me) if raw_me else _default_month_end()
    month_start = month_end.replace(day=1)
    live = os.environ.get("LIVE", "0") == "1"
    force = os.environ.get("FORCE", "0") == "1"

    p("# Phase 5.7 / Step 9a -- Month-Close LOCK")
    p("")
    p(f"- **Target month-end**: `{month_end.isoformat()}`")
    p(f"- **Mode**: {'LIVE (writes)' if live else 'DRY-RUN (no writes)'}")
    p(f"- **Force**: {'YES (ignoring blockers)' if force else 'no'}")
    p(f"- **Run by**: `{frappe.session.user}`  at `{datetime.utcnow().isoformat()}Z`")
    p("")

    # ---- sanity guards ----
    today = date.today()
    if month_end > today:
        p(f"**ABORT** -- MONTH_END `{month_end}` is in the future. Refusing to lock a period that hasn't ended.")
        _save(L)
        return
    # New guardrail (Q2-d): refuse to lock on the last day of the target month
    # itself, because same-day POS activity (invoices dated month_end) gets
    # trapped INSIDE the freeze window (ERPNext freeze comparison is inclusive).
    # Standard finance practice: run the lock on month_end + 1 or later.
    if today <= month_end and not force:
        p(f"**ABORT** -- today (`{today}`) is on/before MONTH_END (`{month_end}`).")
        p("")
        p("Locking on the last day of a month traps same-day activity inside the freeze")
        p("window because ERPNext's freeze comparison is inclusive (`<=`). Wait until the")
        p("first working day of the following month, then re-run.")
        p("")
        p("If you understand this risk and need to override (e.g. parallel-run testing),")
        p("re-run with `FORCE=1` AND ensure no further activity on/before MONTH_END is")
        p("possible (all POS shifts closed, all draft invoices submitted).")
        _save(L)
        return
    if (today - month_end).days > 90:
        p(f"**ABORT** -- MONTH_END `{month_end}` is more than 90 days in the past ({(today - month_end).days} days). "
          f"Locking that far back requires manual intervention by HOD Finance + IT.")
        _save(L)
        return
    if not _is_last_day_of_month(month_end):
        p(f"> :warning: MONTH_END is **not** the last day of its month. This is unusual but allowed.")
        p("")

    cur_stock = frappe.db.get_single_value("Stock Settings", "stock_frozen_upto")
    cur_acc = frappe.db.get_single_value("Accounts Settings", "acc_frozen_upto")
    p("## Current settings")
    p(f"- `Stock Settings.stock_frozen_upto` = `{cur_stock}`")
    p(f"- `Accounts Settings.acc_frozen_upto` = `{cur_acc}`")
    p("")

    will_set_stock = (not cur_stock) or (cur_stock < month_end)
    will_set_acc = (not cur_acc) or (cur_acc < month_end)
    p("## Planned change")
    p(f"- stock_frozen_upto: `{cur_stock}` -> `{month_end}`  "
      f"{'(WILL CHANGE)' if will_set_stock else '(no-op; already >= target)'}")
    p(f"- acc_frozen_upto:   `{cur_acc}` -> `{month_end}`  "
      f"{'(WILL CHANGE)' if will_set_acc else '(no-op; already >= target)'}")
    p("")

    if not will_set_stock and not will_set_acc:
        p("**Both freeze dates already >= target. Nothing to do.**")
        _save(L)
        return

    # ---- pre-check blockers ----
    p("## Pre-check (inline)")
    blockers = _precheck_blockers(month_end, month_start)
    if blockers:
        p(f"- **{len(blockers)} blocker(s) found:**")
        for b in blockers:
            p(f"  - {b}")
        p("")
        if not force:
            p("**ABORT** -- blockers present. Resolve them then re-run, or pass `FORCE=1` "
              "ONLY with HOD Finance written approval.")
            _save(L)
            return
        else:
            p("**FORCE=1 set** -- proceeding despite blockers. This must be authorised "
              "by HOD Finance in writing and recorded in the close binder.")
            p("")
    else:
        p("- No blockers found. Safe to proceed.")
        p("")

    # ---- write or simulate ----
    if not live:
        p("## DRY-RUN -- no changes made")
        p("")
        p("Re-run with `LIVE=1` to apply.")
        _save(L)
        return

    p("## Applying changes")
    if will_set_stock:
        frappe.db.set_single_value("Stock Settings", "stock_frozen_upto", month_end)
        p(f"- stock_frozen_upto set to `{month_end}`")
    if will_set_acc:
        frappe.db.set_single_value("Accounts Settings", "acc_frozen_upto", month_end)
        p(f"- acc_frozen_upto set to `{month_end}`")
    frappe.db.commit()
    p("- COMMITTED.")
    p("")

    # verify
    v_stock = frappe.db.get_single_value("Stock Settings", "stock_frozen_upto")
    v_acc = frappe.db.get_single_value("Accounts Settings", "acc_frozen_upto")
    p("## Verification")
    p(f"- `Stock Settings.stock_frozen_upto` = `{v_stock}`")
    p(f"- `Accounts Settings.acc_frozen_upto` = `{v_acc}`")
    p("")
    if v_stock == month_end and v_acc == month_end:
        p("**OK** -- both freeze dates confirmed.")
    else:
        p("**WARNING** -- post-write values do not match target. Investigate immediately.")
    p("")
    p("Attach this log to the close binder at /Finance/MonthClose/<YYYY-MM>/Lock/.")

    _save(L)


def _save(L: list[str]) -> None:
    out = "\n".join(L)
    Path("/tmp/p57_monthclose_lock.log").write_text(out, encoding="utf-8")
    print(out)
    print()
    print(f"  Full log: /tmp/p57_monthclose_lock.log")


main()
