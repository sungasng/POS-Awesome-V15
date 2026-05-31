"""
p57: Remove Territory User Permissions from cashiers / plant managers so
they can sell to ANY customer (cross-territory customers like Gesho).

Background:
  The Territory User Permission was set up as a default-value convenience
  but Frappe applies it as a HARD FILTER. This blocks POS consolidation
  whenever a shift contains a sale to a customer in a different territory.

Scope:
  - Removes Territory User Permissions ONLY for users holding the
    `LPG POS User` role (cashiers + plant managers).
  - Does NOT touch Administrator or other roles.
  - DRY-RUN by default. Set LIVE=1 to apply.

Parameters:
    LIVE    "1" to delete. Default "0" (dry-run).
"""
from __future__ import annotations
from pathlib import Path
import os
import frappe


def main():
    L = []
    p = L.append
    live = os.environ.get("LIVE", "0") == "1"
    p("# p57 -- Remove Territory User Permissions from cashiers / plant managers")
    p("")
    p(f"- Mode: {'LIVE' if live else 'DRY-RUN'}")
    p("")

    # Users with LPG POS User role
    pos_users = [r["parent"] for r in frappe.db.sql("""
        select distinct parent from `tabHas Role`
        where role = 'LPG POS User' and parenttype = 'User'
    """, as_dict=True)]
    pos_users = [u for u in pos_users if u not in ("Administrator", "Guest")]
    p(f"- Cashier-shaped users (have LPG POS User role): **{len(pos_users)}**")
    p("")

    rows = frappe.db.sql("""
        select name, user, allow, for_value, applicable_for, apply_to_all_doctypes
        from `tabUser Permission`
        where allow = 'Territory' and user in %s
        order by user
    """, (tuple(pos_users),), as_dict=True)

    p(f"Found **{len(rows)}** Territory User Permission row(s) to delete.")
    p("")
    if not rows:
        p("Nothing to do.")
        _save(L); return

    p("| # | User | Territory | applicable_for | apply_to_all |")
    p("|---|------|-----------|----------------|--------------|")
    for i, r in enumerate(rows, 1):
        p(f"| {i} | {r['user']} | {r['for_value']} | "
          f"{r['applicable_for'] or '(none)'} | {r['apply_to_all_doctypes']} |")
    p("")

    if not live:
        p("**DRY-RUN** -- re-run with `LIVE=1` to delete.")
        _save(L); return

    ok, failed = 0, []
    for r in rows:
        try:
            frappe.delete_doc("User Permission", r["name"], ignore_permissions=True)
            ok += 1
        except Exception as e:
            failed.append((r["name"], str(e)))
    frappe.db.commit()
    p(f"**Deleted**: {ok}")
    p(f"**Failed**: {len(failed)}")
    if failed:
        for n, err in failed:
            p(f"- {n}: {err}")
    p("")
    p("## Next steps")
    p("1. Affected users (cashiers / plant managers) LOG OUT then LOG IN.")
    p("2. Peace re-attempts Close Shift on POSA-OS-26-0000003.")
    p("3. Re-run precheck for May 2026 close.")
    p("")
    p("## Default Territory on new customers (replacement mechanism)")
    p("If you want NEW customers created at Ikeja to default to Territory=Ikeja,")
    p("set the `territory` field on the POS Profile `POS - Ikeja`. The cashier")
    p("can override on each sale if needed.")
    _save(L)


def _save(L):
    out = "\n".join(L)
    Path("/tmp/p57_remove_terr_up.log").write_text(out, encoding="utf-8")
    print(out)
    print()
    print(f"  Log: /tmp/p57_remove_terr_up.log")


main()
