"""
Phase 5.7 -- Diagnose and (optionally) repair POS user role assignments.

Read-only by default. Set LIVE=1 to apply fixes.

For each user in USERS (or all enabled users if USERS empty):
  - Show: enabled, role_profile_name, roles (filtered to POS-relevant), missing roles.
  - Recommend assignment of "LPG POS User" Role Profile if any required role is missing
    AND the user already has at least one POS-related role (i.e. cashier-shaped).

Required roles for a working POS Awesome cashier (per assign_cashier_roles.py):
  Sales User, Stock User, Accounts User, LPG POS User.

Parameters (environment variables):
    USERS           Comma-separated list of usernames/emails. Default = "peace.effiong@sungas.org"
    LIVE            "1" to actually assign the Role Profile. Default "0" (dry-run).

Run (replace SHA):
    SHA=<commit>
    export USERS='peace.effiong@sungas.org'
    cd ~/frappe-bench
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/$SHA/scripts/p57_fix_cashier_permissions.py" -o /tmp/p57fix.py
    bench --site sungasmis.v.frappe.cloud execute "(exec(open('/tmp/p57fix.py').read(), globals()) or (lambda **k: None))"
    # then LIVE=1
    export LIVE=1
    bench --site sungasmis.v.frappe.cloud execute "(exec(open('/tmp/p57fix.py').read(), globals()) or (lambda **k: None))"
"""
from __future__ import annotations
from pathlib import Path
import os
import frappe

REQUIRED_ROLES = {"Sales User", "Stock User", "Accounts User", "LPG POS User"}
TARGET_ROLE_PROFILE = "LPG POS User"


def main() -> None:
    L: list[str] = []
    p = L.append
    p("# POS Cashier Permission Diagnostic + Repair")
    p("")

    live = os.environ.get("LIVE", "0") == "1"
    users_csv = os.environ.get("USERS", "peace.effiong@sungas.org").strip()
    targets = [u.strip() for u in users_csv.split(",") if u.strip()]
    p(f"- Mode: {'LIVE (writes)' if live else 'DRY-RUN'}")
    p(f"- Users: {targets}")
    p("")

    if not frappe.db.exists("Role Profile", TARGET_ROLE_PROFILE):
        p(f"**ABORT**: Role Profile '{TARGET_ROLE_PROFILE}' does not exist. "
          f"Run assign_cashier_roles.py first.")
        _save(L); return

    will_assign: list[tuple[str, list[str]]] = []
    already_ok: list[str] = []

    for u in targets:
        p(f"## {u}")
        if not frappe.db.exists("User", u):
            p("- User does not exist.")
            p("")
            continue
        user = frappe.get_doc("User", u)
        p(f"- Enabled: {user.enabled}")
        p(f"- Current role_profile_name: `{user.role_profile_name or '(none)'}`")
        current_roles = {r.role for r in user.roles}
        relevant = sorted(current_roles & (REQUIRED_ROLES | {"LPG Plant Manager",
                                                            "LPG Head of Sales",
                                                            "LPG Head of Finance"}))
        p(f"- POS-relevant roles currently assigned: {relevant or '(none)'}")
        missing = sorted(REQUIRED_ROLES - current_roles)
        p(f"- Missing required roles: {missing or '(none)'}")
        if not missing:
            p(f"- **OK** -- already has all required POS roles. No change needed.")
            already_ok.append(u)
        else:
            p(f"- **WILL ASSIGN** Role Profile `{TARGET_ROLE_PROFILE}`.")
            will_assign.append((u, missing))
        p("")

    if not will_assign:
        p("## Summary: nothing to do.")
        _save(L); return

    if not live:
        p("## Summary (DRY-RUN)")
        p("| User | Missing roles | Action |")
        p("|------|---------------|--------|")
        for u, missing in will_assign:
            p(f"| {u} | {', '.join(missing)} | assign Role Profile `{TARGET_ROLE_PROFILE}` |")
        p("")
        p("Re-run with `LIVE=1` to apply.")
        _save(L); return

    p("## Applying")
    ok, failed = [], []
    for u, _ in will_assign:
        try:
            user = frappe.get_doc("User", u)
            user.role_profile_name = TARGET_ROLE_PROFILE
            # save() will populate roles from the profile
            user.save(ignore_permissions=True)
            ok.append(u)
            p(f"- :white_check_mark: assigned `{TARGET_ROLE_PROFILE}` to {u}")
        except Exception as e:
            failed.append((u, str(e)))
            p(f"- :x: FAILED {u}: {e}")
    frappe.db.commit()
    p("")
    p(f"**OK**: {len(ok)}    **Failed**: {len(failed)}")
    _save(L)


def _save(L: list[str]) -> None:
    out = "\n".join(L)
    Path("/tmp/p57_fix_cashier_permissions.log").write_text(out, encoding="utf-8")
    print(out)
    print()
    print(f"  Log: /tmp/p57_fix_cashier_permissions.log")


main()
