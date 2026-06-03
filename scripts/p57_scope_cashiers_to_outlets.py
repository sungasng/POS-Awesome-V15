"""p57_scope_cashiers_to_outlets.py
==================================
Apply User Permission scoping so cashiers only see records from their own
outlet (POS Profile + Cost Center + Warehouse + Branch).

Discovered 2026-06-03: Peace Effiong (cashier @ Ikeja) could see POS Opening
Shifts from Ebute outlet in the desk list view. Frappe's User Permission
system was never seeded for cashier accounts after the May 2026 outlet clone.

This script:
  1. Reads the existing User-to-POS-Profile mapping by scanning
     POS Profile User child tables (set during the cashier role rollout).
  2. For each cashier user, inserts (idempotent) User Permission rows:
       - POS Profile = their assigned profile
       - Cost Center = the profile's cost center
       - Warehouse = the profile's warehouse
       - Branch = the profile's branch (if set)
  3. Reports who got scoped, who was already scoped, and who was skipped.

Roles excluded from scoping (full visibility retained):
  - System Manager
  - Accounts Manager
  - LPG Head of Operations
  - LPG Head of Sales
  - LPG Head of Finance
  - HR Manager
  - Anyone with desk role 'POS Manager' or 'Sales Manager'

Run:
  bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/p57_scope.py').read())"
"""
import frappe  # type: ignore # noqa: F401

# Roles that grant cross-outlet visibility -- if a user holds any of these,
# we DO NOT add restrictive User Permissions.
EXEMPT_ROLES = {
    "System Manager",
    "Accounts Manager",
    "LPG Head of Operations",
    "LPG Head of Sales",
    "LPG Head of Finance",
    "HR Manager",
    "POS Manager",
    "Sales Manager",
    "Auditor",
}


def main():
    # Step 1: pull all POS Profile -> User mappings from the child table.
    rows = frappe.db.sql(
        """
        SELECT
            ppu.user      AS user_id,
            ppu.parent    AS pos_profile,
            pp.cost_center,
            pp.warehouse,
            pp.branch
        FROM `tabPOS Profile User` ppu
        INNER JOIN `tabPOS Profile` pp ON pp.name = ppu.parent
        WHERE pp.disabled = 0
        """,
        as_dict=True,
    )

    by_user = {}
    for r in rows:
        by_user.setdefault(r.user_id, []).append(r)

    scoped, skipped_exempt, already, errors = [], [], [], []
    for user_id, profile_rows in by_user.items():
        # Skip exempt roles
        user_roles = {
            r.role
            for r in frappe.db.get_all(
                "Has Role", filters={"parent": user_id}, fields=["role"]
            )
        }
        if user_roles & EXEMPT_ROLES:
            skipped_exempt.append((user_id, list(user_roles & EXEMPT_ROLES)))
            continue

        # Build the set of (doctype, value) tuples we want for this user
        targets = set()
        for r in profile_rows:
            targets.add(("POS Profile", r.pos_profile))
            if r.cost_center:
                targets.add(("Cost Center", r.cost_center))
            if r.warehouse:
                targets.add(("Warehouse", r.warehouse))
            if r.branch:
                targets.add(("Branch", r.branch))

        # Insert missing User Permissions (idempotent)
        added_here = []
        for allow_dt, allow_val in sorted(targets):
            exists = frappe.db.exists(
                "User Permission",
                {
                    "user": user_id,
                    "allow": allow_dt,
                    "for_value": allow_val,
                },
            )
            if exists:
                already.append((user_id, allow_dt, allow_val))
                continue
            try:
                up = frappe.get_doc({
                    "doctype": "User Permission",
                    "user": user_id,
                    "allow": allow_dt,
                    "for_value": allow_val,
                    "apply_to_all_doctypes": 1,
                    "is_default": 0,
                })
                up.insert(ignore_permissions=True)
                added_here.append((allow_dt, allow_val))
            except Exception as e:
                errors.append((user_id, allow_dt, allow_val, str(e)))

        if added_here:
            scoped.append((user_id, added_here))

    frappe.db.commit()

    print("\n=== User Permission Scoping Report ===")
    print(f"Cashiers scoped: {len(scoped)}")
    for u, perms in scoped:
        print(f"  + {u}")
        for dt, val in perms:
            print(f"      {dt}: {val}")
    print(f"\nAlready scoped (no change): {len(already)} permission rows")
    print(f"\nExempted (cross-outlet roles): {len(skipped_exempt)}")
    for u, roles in skipped_exempt:
        print(f"  - {u}  [{', '.join(roles)}]")
    if errors:
        print(f"\nErrors: {len(errors)}")
        for u, dt, val, err in errors:
            print(f"  ! {u} {dt}={val}: {err}")
    print()


main()
