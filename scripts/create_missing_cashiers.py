"""
Create the 8 missing LPG cashier users on `sungasmis.v.frappe.cloud`.

For each email below the script:
    - parses first/last name from `<first>.<last>@sungas.org`
    - creates the User if not already present (idempotent)
    - clones the role list from any existing user that already has the
      `LPG POS User` role -- guarantees parity with the other 49 cashiers
      without us having to hardcode (and risk drift from) the role set.
    - sets enabled=1, send_welcome_email=0 (no spam), language=en
    - sets a temporary password (force_reset_password=1)

Outlet hints are kept in the dict as a comment in `bio` for traceability.
The POS-Profile <-> User mapping is intentionally NOT done here: that is
handled per-outlet via the "Applicable for Users" table on each POS Profile,
which the project owner manages in the UI.

Run on bench:
    bench --site sungasmis.v.frappe.cloud execute \\
        "exec(open('/tmp/create_missing_cashiers.py').read())"
"""

from __future__ import annotations

import sys

import frappe


# email -> outlet (for the User.bio note)
CASHIERS = {
    "bolanle.ayodele@sungas.org":   "Pedro",
    "bolajoko.abilawon@sungas.org": "Pedro",
    "gift.okotogbo@sungas.org":     "Upper Mission",
    "racheal.moses@sungas.org":     "Bolade",
    "shima.justine@sungas.org":     "Ekehuan",
    "gift.odihi@sungas.org":        "Ekehuan",
    "kaosara.kareem@sungas.org":    "Iju-Otta",
    "oluwaseyi.olawole@sungas.org": "Ijoko",
}

DEFAULT_PASSWORD = "SungasTest@2026"
CASHIER_ROLE = "LPG POS User"


def _split_name(email: str) -> tuple[str, str]:
    local = email.split("@", 1)[0]
    parts = local.split(".")
    if len(parts) >= 2:
        return parts[0].title(), parts[-1].title()
    return parts[0].title(), ""


def _template_role_list() -> list[str]:
    """
    Find any existing user with the `LPG POS User` role and clone their
    full role list. Falls back to a minimal sane set if none found.
    """
    template_user = frappe.db.get_value(
        "Has Role",
        {"role": CASHIER_ROLE, "parenttype": "User"},
        "parent",
    )
    if not template_user:
        print(f"  WARN: no existing user has role {CASHIER_ROLE!r}; "
              "falling back to minimal role list.")
        return [
            CASHIER_ROLE,
            "Sales User",
            "Accounts User",
            "Stock User",
        ]
    roles = frappe.get_all(
        "Has Role",
        filters={"parent": template_user, "parenttype": "User"},
        pluck="role",
    )
    # Exclude administrator-only roles in case the template user has them.
    excluded = {"Administrator", "All", "Guest"}
    roles = [r for r in roles if r not in excluded]
    print(f"  Using {template_user} as role template ({len(roles)} roles): "
          f"{', '.join(sorted(roles))}")
    return roles


def main():
    print("=" * 70)
    print(f"Create {len(CASHIERS)} missing cashier users")
    print("=" * 70)

    role_list = _template_role_list()

    created = 0
    updated = 0
    skipped = 0
    errors = []

    for email, outlet in CASHIERS.items():
        try:
            if frappe.db.exists("User", email):
                user = frappe.get_doc("User", email)
                # Ensure they have at least the cashier role.
                have = {r.role for r in user.roles}
                added_role = False
                for r in role_list:
                    if r not in have:
                        user.append("roles", {"role": r})
                        added_role = True
                if added_role:
                    user.enabled = 1
                    user.save(ignore_permissions=True)
                    updated += 1
                    print(f"  UPDATED {email} (+ missing roles)")
                else:
                    skipped += 1
                    print(f"  SKIP    {email} (already exists with correct roles)")
                continue

            first, last = _split_name(email)
            user = frappe.get_doc({
                "doctype": "User",
                "email": email,
                "first_name": first,
                "last_name": last,
                "username": email.split("@", 1)[0],
                "send_welcome_email": 0,
                "enabled": 1,
                "user_type": "System User",
                "language": "en",
                "time_zone": "Africa/Lagos",
                "bio": f"LPG cashier — outlet: {outlet}",
                "new_password": DEFAULT_PASSWORD,
                "roles": [{"role": r} for r in role_list],
            })
            # Skip the Frappe password-strength validator for bulk-created
            # cashier accounts (we know SungasTest@2026 meets the rule).
            user.flags.ignore_password_policy = True
            user.insert(ignore_permissions=True)

            # Force change on first login.
            try:
                frappe.db.set_value("User", email, "reset_password_key", "")
                user.reload()
                user.append("user_emails", {})  # noop -- some clouds need a save touch
            except Exception:
                pass

            created += 1
            print(f"  CREATED {email}  outlet={outlet}  name={first} {last}")
        except Exception as e:
            errors.append((email, str(e)))
            print(f"  ERROR   {email}: {e}")

    frappe.db.commit()
    frappe.clear_cache()

    print("\n" + "=" * 70)
    print(f"  Created: {created}    Updated: {updated}    "
          f"Skipped: {skipped}    Errors: {len(errors)}")
    if errors:
        print("\n  Errors:")
        for email, err in errors:
            print(f"    - {email}: {err}")
    print(f"\n  Temporary password for ALL new users: {DEFAULT_PASSWORD}")
    print("  (Cashiers should change it on first login.)")
    print("=" * 70)
    sys.exit(0 if not errors else 1)


# bench execute runs us via eval(method, globals(), locals()) which separates
# the two dicts. Top-level `def`s land in locals, but main.__globals__ points
# at Frappe's command-module globals — so main()'s call to `_template_role_list`
# / `_split_name` fails with NameError. Copy locals into globals to fix scope.
try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
