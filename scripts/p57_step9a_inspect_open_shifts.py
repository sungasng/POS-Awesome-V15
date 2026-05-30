"""
Phase 5.7 / Step 9a -- Inspect open POS Opening Shifts.

Read-only. For every POS Opening Shift currently in status='Open' (docstatus=1),
shows:
  - profile, cashier, period start
  - submitted POS Invoices linked to that shift (count, total, last invoice date)
  - whether the shift is "empty" (safe to cancel) or "has invoices" (must close
    properly via POS Awesome > Close Shift)

Helps decide cancel-vs-close before the month lock.

Run (replace SHA):
    SHA=<commit>
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/$SHA/scripts/p57_step9a_inspect_open_shifts.py" -o /tmp/p57sh.py
    bench --site sungasmis.v.frappe.cloud execute "(exec(open('/tmp/p57sh.py').read(), globals()) or (lambda **k: None))"

Output: stdout + /tmp/p57_open_shifts.md
"""
from __future__ import annotations
from pathlib import Path
import frappe


def main() -> None:
    L: list[str] = []
    p = L.append
    p("# Phase 5.7 / Step 9a -- Open POS Opening Shifts inspection")
    p("")
    p("Read-only. Use this to decide cancel-vs-close per shift.")
    p("")

    shifts = frappe.db.sql("""
        select name, pos_profile, period_start_date, user, company, status
        from `tabPOS Opening Shift`
        where docstatus = 1 and status = 'Open'
        order by period_start_date
    """, as_dict=True)

    if not shifts:
        p("**No open shifts. Nothing to inspect.**")
        _save(L); return

    p(f"Found **{len(shifts)}** open shift(s):")
    p("")

    summary: list[dict] = []
    for s in shifts:
        p(f"## {s['name']}")
        p(f"- Profile: `{s['pos_profile']}`")
        p(f"- Cashier (user): `{s['user']}`")
        p(f"- Period start: `{s['period_start_date']}`")
        p(f"- Company: `{s['company']}`")

        # POS Invoices linked to this shift (POS Awesome links via pos_opening_shift)
        rows_link = []
        try:
            rows_link = frappe.db.sql("""
                select name, docstatus, posting_date, customer, grand_total
                from `tabPOS Invoice`
                where posa_pos_opening_shift = %s
                order by posting_date desc
            """, (s["name"],), as_dict=True)
        except Exception:
            # Fallback to the standard field if posa_pos_opening_shift doesn't exist
            try:
                rows_link = frappe.db.sql("""
                    select name, docstatus, posting_date, customer, grand_total
                    from `tabPOS Invoice`
                    where pos_opening_shift = %s
                    order by posting_date desc
                """, (s["name"],), as_dict=True)
            except Exception as e:
                p(f"- (Could not query linked POS Invoices: {e})")

        submitted = [r for r in rows_link if r["docstatus"] == 1]
        drafts = [r for r in rows_link if r["docstatus"] == 0]
        cancelled = [r for r in rows_link if r["docstatus"] == 2]

        total = sum(float(r["grand_total"] or 0) for r in submitted)
        p(f"- Linked POS Invoices: submitted=**{len(submitted)}**, "
          f"drafts=**{len(drafts)}**, cancelled=**{len(cancelled)}**")
        p(f"- Submitted total: **NGN {total:,.2f}**")
        if submitted:
            last = submitted[0]
            p(f"- Last submitted invoice: {last['name']} on {last['posting_date']} "
              f"(customer: {last['customer']}, NGN {float(last['grand_total'] or 0):,.2f})")
        if drafts:
            p(f"- :warning: {len(drafts)} draft invoice(s) linked -- submit or cancel first")
            for d in drafts[:5]:
                p(f"  - {d['name']} | {d['posting_date']} | NGN {float(d['grand_total'] or 0):,.2f}")

        # Decision
        if len(submitted) + len(drafts) == 0:
            decision = "EMPTY -> safe to CANCEL the Opening Shift (no business impact)."
        elif len(submitted) > 0 and len(drafts) == 0:
            decision = ("HAS REAL SALES -> must be CLOSED via POS Awesome > Close Shift "
                        "(reconcile cash/card/transfer). Do NOT cancel.")
        else:
            decision = ("MIXED state (draft invoices present) -> first submit or cancel the "
                        "drafts, then close the shift via POS Awesome.")
        p(f"- **Recommended action**: {decision}")
        p("")

        summary.append({
            "shift": s["name"],
            "profile": s["pos_profile"],
            "user": s["user"],
            "submitted": len(submitted),
            "drafts": len(drafts),
            "total": total,
            "decision": decision,
        })

    # Summary table
    p("---")
    p("")
    p("## Summary table")
    p("")
    p("| Shift | Profile | Cashier | Submitted | Drafts | Total NGN | Action |")
    p("|-------|---------|---------|-----------|--------|-----------|--------|")
    for r in summary:
        p(f"| {r['shift']} | {r['profile']} | {r['user']} | {r['submitted']} | "
          f"{r['drafts']} | {r['total']:,.2f} | {r['decision'].split(' -> ')[0]} |")
    p("")

    _save(L)


def _save(L: list[str]) -> None:
    out = "\n".join(L)
    Path("/tmp/p57_open_shifts.md").write_text(out, encoding="utf-8")
    print(out)
    print()
    print(f"  Full report: /tmp/p57_open_shifts.md")


main()
