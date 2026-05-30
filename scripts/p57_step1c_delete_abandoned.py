"""
Phase 5.7 / Step 1c: Bulk-delete categorised 'Abandoned' Draft POS invoices.

Read-only by default. Set DRY_RUN=False to actually delete.

Only deletes Sales Invoices where ALL of:
  - docstatus = 0 (Draft)
  - is_pos = 1
  - age > AGE_THRESHOLD_HOURS
  - posa_is_printed = 0 (cashier never printed -> never gave receipt)
  - no Payment Entry rows attached
  - pos_profile NOT IN PROTECT_PROFILES (whitelist of profiles to leave alone)
"""

from __future__ import annotations
import frappe


DRY_RUN              = True
AGE_THRESHOLD_HOURS  = 24
PROTECT_PROFILES     = set()    # e.g., {"POS - Ikeja"} if you want to keep Ikeja for now


def main() -> None:
    rows = frappe.db.sql("""
        select si.name, si.pos_profile, si.customer, si.grand_total,
               TIMESTAMPDIFF(HOUR, si.creation, NOW()) as age_hr
        from `tabSales Invoice` si
        where si.docstatus = 0
          and si.is_pos = 1
          and coalesce(si.posa_is_printed, 0) = 0
          and TIMESTAMPDIFF(HOUR, si.creation, NOW()) >= %s
          and not exists (select 1 from `tabSales Invoice Payment`
                          where parent = si.name and amount > 0)
        order by si.pos_profile, si.creation
    """, (AGE_THRESHOLD_HOURS,), as_dict=True)

    candidates = [r for r in rows if r["pos_profile"] not in PROTECT_PROFILES]

    print("=" * 72)
    print(f" Step 1c -- Delete abandoned Draft POS invoices  (DRY_RUN={DRY_RUN})")
    print("=" * 72)
    print(f"  Candidates: {len(candidates)}")

    if not candidates:
        print("  Nothing to do.")
        return

    by_pp: dict[str, int] = {}
    for r in candidates:
        by_pp[r["pos_profile"]] = by_pp.get(r["pos_profile"], 0) + 1
    print("  By POS Profile:")
    for pp, n in by_pp.items():
        print(f"    - {pp}: {n}")

    if DRY_RUN:
        print()
        print("  [DRY_RUN] Set DRY_RUN=False to actually delete.")
        return

    deleted = errored = 0
    for r in candidates:
        try:
            frappe.delete_doc("Sales Invoice", r["name"],
                              force=True, ignore_permissions=True)
            deleted += 1
        except Exception as e:
            print(f"  ! {r['name']}: {e!s}")
            errored += 1
    frappe.db.commit()
    print()
    print(f"  Deleted: {deleted}  |  Errored: {errored}")


try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
