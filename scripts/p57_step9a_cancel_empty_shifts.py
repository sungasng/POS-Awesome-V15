"""
Phase 5.7 / Step 9a -- Cancel EMPTY open POS Opening Shifts.

Safety design:
  - Cancels only POS Opening Shifts that are docstatus=1, status='Open'
    AND have ZERO submitted, ZERO draft, ZERO cancelled POS Invoices linked.
  - Defaults to DRY-RUN. Set LIVE=1 to actually cancel.
  - Optionally restrict by PROFILE_LIKE (SQL LIKE) -- e.g. "%Test%" to only
    touch the test profile shifts we identified.

Parameters (environment variables):
    LIVE            "1" to actually cancel. Default "0" (dry-run).
    PROFILE_LIKE    Optional. If set, only profiles matching this LIKE pattern
                    are eligible. Example: "%Test%".

Run (replace SHA):
    SHA=<commit>
    export PROFILE_LIKE='%Test%'
    # 1) DRY-RUN first
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/$SHA/scripts/p57_step9a_cancel_empty_shifts.py" -o /tmp/p57cs.py
    bench --site sungasmis.v.frappe.cloud execute "(exec(open('/tmp/p57cs.py').read(), globals()) or (lambda **k: None))"
    # 2) Re-run with LIVE=1 to apply
    export LIVE=1
    bench --site sungasmis.v.frappe.cloud execute "(exec(open('/tmp/p57cs.py').read(), globals()) or (lambda **k: None))"

Output: stdout + /tmp/p57_cancel_empty_shifts.log
"""

from __future__ import annotations
from pathlib import Path
from datetime import datetime
import os
import frappe


def _linked_invoice_counts(shift_name: str) -> dict:
    """Return submitted/draft/cancelled counts of POS Invoices linked to a shift."""
    field = None
    try:
        # POS Awesome custom field
        frappe.db.sql("select 1 from `tabPOS Invoice` where posa_pos_opening_shift = %s limit 1",
                      (shift_name,))
        field = "posa_pos_opening_shift"
    except Exception:
        try:
            frappe.db.sql("select 1 from `tabPOS Invoice` where pos_opening_shift = %s limit 1",
                          (shift_name,))
            field = "pos_opening_shift"
        except Exception:
            return {"submitted": -1, "draft": -1, "cancelled": -1, "field": None}

    rows = frappe.db.sql(
        f"""
        select docstatus, count(*) as n
        from `tabPOS Invoice`
        where {field} = %s
        group by docstatus
        """,
        (shift_name,),
        as_dict=True,
    )
    out = {"submitted": 0, "draft": 0, "cancelled": 0, "field": field}
    for r in rows:
        if r["docstatus"] == 0:
            out["draft"] = r["n"]
        elif r["docstatus"] == 1:
            out["submitted"] = r["n"]
        elif r["docstatus"] == 2:
            out["cancelled"] = r["n"]
    return out


def main() -> None:
    L: list[str] = []
    p = L.append

    live = os.environ.get("LIVE", "0") == "1"
    profile_like = os.environ.get("PROFILE_LIKE")

    p("# Phase 5.7 / Step 9a -- Cancel EMPTY open POS Opening Shifts")
    p("")
    p(f"- **Mode**: {'LIVE (writes)' if live else 'DRY-RUN (no writes)'}")
    p(f"- **Profile filter (LIKE)**: `{profile_like or '(none, all profiles)'}`")
    p(f"- **Run by**: `{frappe.session.user}`  at `{datetime.utcnow().isoformat()}Z`")
    p("")

    q = """
        select name, pos_profile, period_start_date, user
        from `tabPOS Opening Shift`
        where docstatus = 1 and status = 'Open'
    """
    params = []
    if profile_like:
        q += " and pos_profile like %s"
        params.append(profile_like)
    q += " order by period_start_date"

    shifts = frappe.db.sql(q, tuple(params), as_dict=True)
    p(f"Found **{len(shifts)}** candidate shift(s).")
    p("")

    will_cancel: list[dict] = []
    skipped: list[dict] = []
    for s in shifts:
        counts = _linked_invoice_counts(s["name"])
        total_linked = (counts["submitted"] + counts["draft"] + counts["cancelled"])
        row = {**s, **counts, "total_linked": total_linked}
        if counts["field"] is None:
            skipped.append({**row, "reason": "Could not query linked POS Invoices"})
            continue
        if total_linked > 0:
            skipped.append({**row, "reason": f"Has {total_linked} linked POS Invoice(s) -- NOT empty"})
        else:
            will_cancel.append(row)

    p("## Will cancel")
    if not will_cancel:
        p("- (none)")
    else:
        p("| Shift | Profile | Cashier | Period start |")
        p("|-------|---------|---------|--------------|")
        for r in will_cancel:
            p(f"| {r['name']} | {r['pos_profile']} | {r['user']} | {r['period_start_date']} |")
    p("")

    p("## Skipped (NOT cancelled)")
    if not skipped:
        p("- (none)")
    else:
        p("| Shift | Profile | Submitted | Drafts | Cancelled | Reason |")
        p("|-------|---------|-----------|--------|-----------|--------|")
        for r in skipped:
            p(f"| {r['name']} | {r['pos_profile']} | {r['submitted']} | {r['draft']} | "
              f"{r['cancelled']} | {r['reason']} |")
    p("")

    if not live:
        p("## DRY-RUN -- no changes made")
        p("Re-run with `LIVE=1` to apply.")
        _save(L)
        return

    if not will_cancel:
        p("## Nothing to do.")
        _save(L)
        return

    p("## Applying cancellations")
    cancelled_ok: list[str] = []
    failed: list[tuple[str, str]] = []
    for r in will_cancel:
        try:
            doc = frappe.get_doc("POS Opening Shift", r["name"])
            doc.cancel()
            cancelled_ok.append(r["name"])
            p(f"- :white_check_mark: cancelled {r['name']}")
        except Exception as e:
            failed.append((r["name"], str(e)))
            p(f"- :x: FAILED {r['name']}: {e}")
    frappe.db.commit()
    p("")
    p(f"**Cancelled OK**: {len(cancelled_ok)}")
    p(f"**Failed**: {len(failed)}")
    p("")
    if failed:
        p("Investigate failures before re-running. The successful cancellations are committed.")

    _save(L)


def _save(L: list[str]) -> None:
    out = "\n".join(L)
    Path("/tmp/p57_cancel_empty_shifts.log").write_text(out, encoding="utf-8")
    print(out)
    print()
    print(f"  Full log: /tmp/p57_cancel_empty_shifts.log")


main()
