"""
p57: Narrow Territory User Permissions so they don't block POS Closing Shift consolidation.

Problem
=======
Cashiers have a User Permission row:
    allow = "Territory", for_value = "<their outlet>",
    apply_to_all_doctypes = 1.
That blanket setting causes ERPNext's POS Invoice Merge Log to fail during
POS Closing Shift submit (it calls Sales Invoice.insert() as the cashier,
the consolidated doc has no territory yet, the territory User Permission
blocks the create).

Fix
===
For each Territory-type User Permission with apply_to_all_doctypes=1:
    - Set apply_to_all_doctypes = 0
    - Set applicable_for = "Customer"
This keeps the intended scope (cashier sees only their outlet's customers
in pickers) but stops blocking unrelated doctypes.

Same logic applied to any apply_to_all=1 User Permission of allow='Cost Center',
'Warehouse' or 'Branch' if such patterns exist -- they have the same risk.

Parameters:
    LIVE        "1" to write. Default "0" (dry-run).
    ALLOW_TYPES Comma-separated list of "allow" doctypes to narrow.
                Default: "Territory"  (add others e.g. "Territory,Cost Center" if needed).
"""
from __future__ import annotations
from pathlib import Path
import os
import frappe

ALLOW_TYPES_DEFAULT = "Territory"
# What to set applicable_for to, per allow doctype
APPLICABLE_FOR_MAP = {
    "Territory": "Customer",
    "Cost Center": "Sales Invoice",
    "Warehouse": "Stock Entry",
    "Branch": "Employee",
}


def main():
    L = []
    p = L.append
    live = os.environ.get("LIVE", "0") == "1"
    allow_types = [x.strip() for x in
                   os.environ.get("ALLOW_TYPES", ALLOW_TYPES_DEFAULT).split(",") if x.strip()]
    p("# p57 -- Narrow Territory User Permissions")
    p("")
    p(f"- Mode: {'LIVE' if live else 'DRY-RUN'}")
    p(f"- Allow types to narrow: {allow_types}")
    p("")

    rows = frappe.db.sql(
        """
        select name, user, allow, for_value, applicable_for, apply_to_all_doctypes
        from `tabUser Permission`
        where apply_to_all_doctypes = 1
          and allow in %s
        order by user, allow
        """,
        (tuple(allow_types),),
        as_dict=True,
    )
    p(f"Found **{len(rows)}** User Permission row(s) needing narrowing.")
    p("")
    if not rows:
        p("Nothing to do.")
        _save(L); return

    p("| # | User | Allow | For value | Will set applicable_for | Apply to all |")
    p("|---|------|-------|-----------|------------------------|--------------|")
    plan = []
    for i, r in enumerate(rows, 1):
        af = APPLICABLE_FOR_MAP.get(r["allow"], "Customer")
        plan.append((r, af))
        p(f"| {i} | {r['user']} | {r['allow']} | {r['for_value']} | {af} | 1 -> 0 |")
    p("")

    if not live:
        p("**DRY-RUN** -- re-run with `LIVE=1` to apply.")
        _save(L); return

    ok, failed = 0, []
    for r, af in plan:
        try:
            up = frappe.get_doc("User Permission", r["name"])
            up.applicable_for = af
            up.apply_to_all_doctypes = 0
            up.save(ignore_permissions=True)
            ok += 1
        except Exception as e:
            failed.append((r["name"], str(e)))
    frappe.db.commit()
    p(f"**Applied**: {ok}")
    p(f"**Failed**: {len(failed)}")
    if failed:
        p("")
        for name, err in failed:
            p(f"- {name}: {err}")

    # Tell the user what to do next
    p("")
    p("## Next steps")
    p("1. Ask the affected cashiers to LOG OUT then LOG IN to refresh their permission cache.")
    p("2. Peace can re-attempt to Submit the POS Closing Shift (POSA-OS-26-0000003).")
    p("3. Re-run the precheck (p57_step9a_monthclose_precheck.py) to confirm 0 blockers.")
    _save(L)


def _save(L):
    out = "\n".join(L)
    Path("/tmp/p57_narrow_user_perm.log").write_text(out, encoding="utf-8")
    print(out)
    print()
    print(f"  Log: /tmp/p57_narrow_user_perm.log")


main()
