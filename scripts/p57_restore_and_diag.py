"""
p57: (a) Restore rasheed.obi role profile (we accidentally downgraded him).
     (b) Deep-diagnose peace.effiong@sungas.org Sales Invoice create permission.

Read-only diagnostic for Peace; LIVE=1 required to actually restore Rasheed.

Run:
    SHA=<commit>
    cd ~/frappe-bench
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/$SHA/scripts/p57_restore_and_diag.py" -o /tmp/p57r.py
    # 1) dry-run -- only diagnoses, no writes
    bench --site sungasmis.v.frappe.cloud execute "(exec(open('/tmp/p57r.py').read(), globals()) or (lambda **k: None))"
    # 2) live -- restores Rasheed
    export LIVE=1
    bench --site sungasmis.v.frappe.cloud execute "(exec(open('/tmp/p57r.py').read(), globals()) or (lambda **k: None))"
"""
from __future__ import annotations
from pathlib import Path
import os
import frappe

RASHEED = "rasheed.obi@sungas.org"
RASHEED_TARGET_PROFILE = "LPG Head of Finance"

PEACE = "peace.effiong@sungas.org"
TARGET_DOCTYPE = "Sales Invoice"


def _restore_rasheed(L, live: bool):
    p = L.append
    p("# 1. Restore Rasheed (assigning him LPG Head of Finance Role Profile)")
    p("")
    if not frappe.db.exists("User", RASHEED):
        p(f"User `{RASHEED}` does not exist. Skipping."); p(""); return
    if not frappe.db.exists("Role Profile", RASHEED_TARGET_PROFILE):
        p(f"Role Profile `{RASHEED_TARGET_PROFILE}` does not exist. ABORT."); p(""); return
    u = frappe.get_doc("User", RASHEED)
    p(f"- Current role_profile_name: `{u.role_profile_name}`")
    p(f"- Current roles: {sorted(r.role for r in u.roles)}")
    if u.role_profile_name == RASHEED_TARGET_PROFILE:
        p(f"- Already on `{RASHEED_TARGET_PROFILE}`. Nothing to do."); p(""); return
    p(f"- Will set role_profile_name to `{RASHEED_TARGET_PROFILE}` "
      f"(this gives back Accounts Manager, LPG Plant Manager, LPG Head of Sales, LPG Head of Finance).")
    if not live:
        p("- DRY-RUN -- not applied.")
        p(""); return
    u.role_profile_name = RASHEED_TARGET_PROFILE
    u.save(ignore_permissions=True)
    frappe.db.commit()
    u = frappe.get_doc("User", RASHEED)
    p(f"- :white_check_mark: applied. New roles: {sorted(r.role for r in u.roles)}")
    p("")


def _diag_peace(L):
    p = L.append
    p(f"# 2. Deep diagnosis: why can't `{PEACE}` create `{TARGET_DOCTYPE}`?")
    p("")
    if not frappe.db.exists("User", PEACE):
        p("Peace's user does not exist. ABORT."); return

    user = frappe.get_doc("User", PEACE)
    roles = sorted(r.role for r in user.roles)
    p(f"- Enabled: {user.enabled}")
    p(f"- Roles: {roles}")
    p("")

    # 2.1 Has permission?
    p("## 2.1 frappe.has_permission as Peace")
    frappe.set_user(PEACE)
    try:
        has = frappe.has_permission(TARGET_DOCTYPE, ptype="create", throw=False)
        p(f"- has_permission('{TARGET_DOCTYPE}', 'create') = **{has}**")
    except Exception as e:
        p(f"- Exception during has_permission: {e}")
    frappe.set_user("Administrator")
    p("")

    # 2.2 DocPerm rows on Sales Invoice for Peace's roles
    p("## 2.2 DocPerm rows on Sales Invoice for Peace's roles")
    perms = frappe.db.sql("""
        select role, permlevel, `read`, `write`, `create`, `submit`, `cancel`, `amend`,
               `if_owner`
        from `tabDocPerm`
        where parent = %s and role in %s
        order by permlevel, role
    """, (TARGET_DOCTYPE, tuple(roles)), as_dict=True)
    if not perms:
        p("- :warning: NO DocPerm rows for Peace's roles -- this WOULD cause the 'not permitted' error.")
    else:
        p("| Role | permlvl | read | write | create | submit | cancel | amend | if_owner |")
        p("|------|---------|------|-------|--------|--------|--------|-------|----------|")
        for r in perms:
            p(f"| {r['role']} | {r['permlevel']} | {r['read']} | {r['write']} | {r['create']} | "
              f"{r['submit']} | {r['cancel']} | {r['amend']} | {r['if_owner']} |")
    p("")

    # 2.3 Custom DocPerm (overrides standard DocPerm)
    p("## 2.3 Custom DocPerm rows on Sales Invoice (if any) for Peace's roles")
    custom = frappe.db.sql("""
        select role, permlevel, `read`, `write`, `create`, `submit`, `cancel`, `amend`
        from `tabCustom DocPerm`
        where parent = %s and role in %s
        order by permlevel, role
    """, (TARGET_DOCTYPE, tuple(roles)), as_dict=True)
    if not custom:
        p("- (none) -- standard DocPerm applies as-is.")
    else:
        p("**Custom DocPerm OVERRIDES the standard DocPerm completely** when present.")
        p("| Role | permlvl | read | write | create | submit | cancel | amend |")
        p("|------|---------|------|-------|--------|--------|--------|-------|")
        for r in custom:
            p(f"| {r['role']} | {r['permlevel']} | {r['read']} | {r['write']} | {r['create']} | "
              f"{r['submit']} | {r['cancel']} | {r['amend']} |")
    p("")

    # 2.4 User Permissions assigned to Peace
    p("## 2.4 User Permissions on Peace")
    ups = frappe.db.sql("""
        select allow, for_value, applicable_for, apply_to_all_doctypes
        from `tabUser Permission`
        where user = %s
        order by allow, for_value
    """, (PEACE,), as_dict=True)
    if not ups:
        p("- (none)")
    else:
        p("| Allow doctype | For value | Applicable for | All doctypes? |")
        p("|---------------|-----------|----------------|---------------|")
        for r in ups:
            p(f"| {r['allow']} | {r['for_value']} | {r['applicable_for'] or '-'} | {r['apply_to_all_doctypes']} |")
        # Sniff for restrictive applicable_for that scopes user only to non-Sales-Invoice contexts
        non_si = [r for r in ups if r["applicable_for"] and r["applicable_for"] != TARGET_DOCTYPE
                  and not r["apply_to_all_doctypes"]]
        if non_si:
            p("")
            p("- (informational) Some User Permissions are scoped to specific doctypes, "
              "not Sales Invoice. That alone shouldn't block create -- but worth noting.")
    p("")

    # 2.5 Active workflow on Sales Invoice
    p("## 2.5 Active Workflow on Sales Invoice (if any)")
    wfs = frappe.db.sql("""
        select name, is_active
        from `tabWorkflow` where document_type = %s
    """, (TARGET_DOCTYPE,), as_dict=True)
    if not wfs:
        p("- (no workflow on Sales Invoice)")
    else:
        for w in wfs:
            p(f"- `{w['name']}` (is_active={w['is_active']})")
    p("")

    # 2.6 Check Cashier role permission level 1+ restrictions
    p("## 2.6 Permission levels > 0 on Sales Invoice for Peace's roles (if any)")
    plus = [r for r in perms if r["permlevel"] > 0]
    if plus:
        p("| Role | permlvl | create | write |")
        p("|------|---------|--------|-------|")
        for r in plus:
            p(f"| {r['role']} | {r['permlevel']} | {r['create']} | {r['write']} |")
    else:
        p("- (none beyond permlevel 0)")
    p("")

    # 2.7 Hypothesis
    p("## 2.7 Diagnosis hypothesis")
    if not custom and any(r["role"] == "Sales User" and r["permlevel"] == 0 and r["create"]
                          for r in perms):
        p("- Sales User has standard create permission. Roles look OK. "
          "Look at User Permissions scope (2.4) and Workflow (2.5).")
    elif custom:
        si_sales_user = next((r for r in custom if r["role"] == "Sales User"
                              and r["permlevel"] == 0), None)
        if si_sales_user and not si_sales_user["create"]:
            p("- :rotating_light: ROOT CAUSE LIKELY: a Custom DocPerm row for `Sales User` "
              "on `Sales Invoice` has `create=0`. This OVERRIDES the standard permission. "
              "Fix: edit that Custom DocPerm row and tick `create`, OR delete the Custom DocPerm "
              "to fall back to default behaviour.")
        else:
            p("- Custom DocPerm rows exist but do not obviously block create. Worth manual review.")
    else:
        p("- Unclear from standard checks. Could be a hooks-level permission_query / has_permission hook "
          "in a custom app. Recommend running `bench --site sungasmis.v.frappe.cloud console` and "
          "executing `frappe.set_user('peace.effiong@sungas.org'); "
          "print(frappe.has_permission('Sales Invoice', 'create', throw=True))` to see the exact "
          "PermissionError traceback.")
    p("")


def main():
    L = []
    live = os.environ.get("LIVE", "0") == "1"
    p = L.append
    p("# p57 -- Restore Rasheed + Deep-Diagnose Peace")
    p("")
    p(f"- Mode: {'LIVE' if live else 'DRY-RUN'}")
    p("")

    _restore_rasheed(L, live)
    _diag_peace(L)

    out = "\n".join(L)
    Path("/tmp/p57_restore_and_diag.log").write_text(out, encoding="utf-8")
    print(out)
    print()
    print(f"  Log: /tmp/p57_restore_and_diag.log")


main()
