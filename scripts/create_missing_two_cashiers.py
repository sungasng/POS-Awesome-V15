"""
Create the 2 cashier users flagged as MISSING by assign_cashier_roles.py:

    emmanuel.nnorom@sungas.org   (Reclamation)
    nimota.sulaimon@sungas.org   (Upper Mission)

Each user is:
    - Enabled = 1
    - send_welcome_email = 0  (no spam mail)
    - Role Profile  = "LPG POS User"  (synchronously syncs roles)
    - User Permission Customer Group = "Retail"
    - Password = SungasTest@2026 (force_reset_password = 0 to keep
      Frappe-Cloud's idle reset behaviour off; first-login reset is
      enforced by the user later in the UI if you want it).

Run on bench (pinned to commit SHA so CDN cache can't bite us):
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/feat/sungas-customizations/scripts/create_missing_two_cashiers.py" \\
      -o /tmp/create_missing_two_cashiers.py && \\
    bench --site sungasmis.v.frappe.cloud execute \\
      "exec(open('/tmp/create_missing_two_cashiers.py').read())"
"""

from __future__ import annotations

import frappe


# email -> (first, last, outlet)
USERS_TO_CREATE = {
    "emmanuel.nnorom@sungas.org": ("Emmanuel", "Nnorom", "Reclamation"),
    "nimota.sulaimon@sungas.org": ("Nimota",   "Sulaimon", "Upper Mission"),
}

ROLE_PROFILE     = "LPG POS User"
CUSTOMER_GROUP   = "Retail"
DEFAULT_PASSWORD = "SungasTest@2026"


def _create_or_update_user(email: str, first: str, last: str, outlet: str) -> str:
    if frappe.db.exists("User", email):
        user = frappe.get_doc("User", email)
        action = "updated"
    else:
        user = frappe.new_doc("User")
        user.email = email
        user.name = email
        user.username = email.split("@", 1)[0]
        action = "created"

    user.first_name = first
    user.last_name = last
    user.enabled = 1
    user.user_type = "System User"
    user.send_welcome_email = 0
    user.language = "en"
    user.bio = f"Cashier - {outlet}"
    user.role_profile_name = ROLE_PROFILE

    # Reset roles so Frappe re-syncs from the role profile on save().
    user.set("roles", [])

    if action == "created":
        user.new_password = DEFAULT_PASSWORD
        user.insert(ignore_permissions=True)
    else:
        user.save(ignore_permissions=True)

    return action


def _ensure_customer_group_perm(email: str) -> bool:
    """Returns True if a new User Permission row was added."""
    if not frappe.db.exists("Customer Group", CUSTOMER_GROUP):
        print(f"  WARN: Customer Group {CUSTOMER_GROUP!r} not found.")
        return False
    if frappe.get_all(
        "User Permission",
        filters={
            "user": email,
            "allow": "Customer Group",
            "for_value": CUSTOMER_GROUP,
        },
        limit=1,
    ):
        return False
    frappe.get_doc({
        "doctype": "User Permission",
        "user": email,
        "allow": "Customer Group",
        "for_value": CUSTOMER_GROUP,
        "apply_to_all_doctypes": 1,
    }).insert(ignore_permissions=True)
    return True


def main():
    print("=" * 78)
    print(" Create 2 missing cashier users + assign LPG POS User profile")
    print("=" * 78)

    if not frappe.db.exists("Role Profile", ROLE_PROFILE):
        print(f"  [FATAL] Role Profile {ROLE_PROFILE!r} not found - "
              "run assign_cashier_roles.py first.")
        return

    # Frappe Cloud's v15 build's User.save() doesn't trigger the
    # queue_action lock dance, so we don't need to monkey-patch here.
    for email, (first, last, outlet) in USERS_TO_CREATE.items():
        action = _create_or_update_user(email, first, last, outlet)
        perm_added = _ensure_customer_group_perm(email)
        suffix = " + perm" if perm_added else ""
        print(f"  [{action:<7}] {email:<40} ({outlet}){suffix}")

    frappe.db.commit()
    print("\n Done. Cashiers can sign in with password:", DEFAULT_PASSWORD)


try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
