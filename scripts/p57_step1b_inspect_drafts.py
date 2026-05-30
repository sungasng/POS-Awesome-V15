"""
Phase 5.7 / Step 1b: Inspect the 23 stale Draft POS invoices found in audit.

Read-only. Pulls full detail on every Draft POS Invoice older than the
audit's 2-hour threshold so we can categorise them before deciding:

  a. Auto-retry submit (likely-good queued jobs that just failed)
  b. Cancel & re-do (mid-sale abandoned -- customer never paid)
  c. Investigate (suspicious -- amounts don't match payment, etc.)

Run:
    SHA=<commit>
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/$SHA/scripts/p57_step1b_inspect_drafts.py" -o /tmp/p57ab.py
    bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/p57ab.py').read())"
"""

from __future__ import annotations
import frappe


def main() -> None:
    print("=" * 78)
    print(" Phase 5.7 / Step 1b -- Stale Draft POS Invoice triage")
    print("=" * 78)
    print()

    rows = frappe.db.sql("""
        select si.name, si.pos_profile, si.owner, si.customer, si.posting_date,
               si.grand_total, si.creation,
               coalesce(si.posa_is_printed, 0) as printed,
               (select sum(amount) from `tabSales Invoice Payment`
                where parent = si.name) as paid,
               TIMESTAMPDIFF(MINUTE, si.creation, NOW()) as age_min,
               (select count(*) from `tabSales Invoice Item`
                where parent = si.name) as line_count
        from `tabSales Invoice` si
        where si.docstatus = 0
          and si.is_pos = 1
          and TIMESTAMPDIFF(MINUTE, si.creation, NOW()) >= 120
        order by si.pos_profile, si.creation
    """, as_dict=True)

    if not rows:
        print("  No stale drafts. Audit data may have been cleaned already.")
        return

    print(f"  Total stale drafts: {len(rows)}")
    print()

    # Group by pos_profile
    by_pp: dict[str, list[dict]] = {}
    for r in rows:
        by_pp.setdefault(r["pos_profile"], []).append(r)

    for pp, items in by_pp.items():
        total = sum(float(r["grand_total"] or 0) for r in items)
        print(f"  === {pp}  |  {len(items)} drafts  |  total NGN {total:,.2f} ===")
        for r in items:
            tag = "PRINTED" if r["printed"] else "       "
            paid = float(r.get("paid") or 0)
            paid_str = f"  paid={paid:>10,.2f}" if paid > 0 else "  paid=     0.00"
            print(f"    {r['name']:<28} {tag}  age={r['age_min']:>5}min  "
                  f"cust={(r['customer'] or '—')[:18]:<18}  "
                  f"total={float(r['grand_total'] or 0):>10,.2f}{paid_str}  "
                  f"lines={r['line_count']}")
        print()

    # Categorise
    likely_good   = [r for r in rows if r["printed"] and float(r.get("paid") or 0) > 0]
    abandoned     = [r for r in rows if not r["printed"]]
    suspicious    = [r for r in rows if r["printed"] and float(r.get("paid") or 0) == 0]

    print("  --- Categorisation ---")
    print(f"  Likely-good (printed + paid)  : {len(likely_good)}  -> step5 auto-retry candidate")
    print(f"  Abandoned (not printed)        : {len(abandoned)}  -> safe to cancel/delete")
    print(f"  Suspicious (printed, unpaid)   : {len(suspicious)}  -> needs manual review")


try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
