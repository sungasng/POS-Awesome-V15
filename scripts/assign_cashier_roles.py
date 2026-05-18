"""
Phase-5.5: build LPG Role Profiles and assign them to plant managers and
cashiers, so they can actually use POS Awesome.

Background
----------
The LPG price-change workflow only installs four ROLES
(LPG POS User, LPG Plant Manager, LPG Head of Sales, LPG Head of Finance).
Those roles alone do not let a user create a POS Sales Invoice -- the
user still needs the regular ERPNext POS roles (Sales User, POS User,
Stock User, Accounts User).

This script wraps each LPG role in a proper Role Profile that bundles
the required ERPNext roles, then assigns the right profile to each
plant manager / cashier from the outlet roster.

Cashiers additionally get a User Permission restricting Customer Group
to "Retail" -- so any new Customer they create from POS lands in the
Retail group, and Wholesale customers are hidden from them.

Run on bench:
    curl -fsSL https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/feat/sungas-customizations/scripts/assign_cashier_roles.py \
      -o /tmp/assign_cashier_roles.py && \
    bench --site sungasmis.v.frappe.cloud execute \
      "exec(open('/tmp/assign_cashier_roles.py').read())"
"""

from __future__ import annotations

import frappe


# ------------------------------------------------------------------ #
# 1.  Role Profile definitions
# ------------------------------------------------------------------ #
# Roles common to every profile (needed to use POS Awesome at all).
POS_BASE_ROLES = [
    "Sales User",
    "POS User",
    "Stock User",
    "Accounts User",
]

ROLE_PROFILES = {
    # Cashiers -- can sell, create Retail customers, hit the LPG workflow.
    "LPG POS User": POS_BASE_ROLES + [
        "LPG POS User",
    ],

    # Plant Managers -- everything cashiers do + approve LPG price changes
    # at their outlet. NO cross-branch visibility (no Sales Manager).
    "LPG Plant Manager": POS_BASE_ROLES + [
        "LPG POS User",
        "LPG Plant Manager",
    ],

    # Head of Sales -- approves LPG price changes at chain level; needs
    # cross-branch sales visibility.
    "LPG Head of Sales": POS_BASE_ROLES + [
        "LPG POS User",
        "LPG Plant Manager",
        "LPG Head of Sales",
        "Sales Manager",
    ],

    # Head of Finance -- final-stage LPG price approval; cross-branch
    # accounting visibility.
    "LPG Head of Finance": POS_BASE_ROLES + [
        "LPG POS User",
        "LPG Plant Manager",
        "LPG Head of Sales",
        "LPG Head of Finance",
        "Accounts Manager",
    ],
}


# ------------------------------------------------------------------ #
# 2.  Users to assign
# ------------------------------------------------------------------ #
PLANT_MANAGERS = {
    "ameh.monday@sungas.org",       # Ikeja
    "cecilia.mathew@sungas.org",    # Pedro
    "john.udoh@sungas.org",         # Bolade
    "adewale.adeniyi@sungas.org",   # Aseese
    "osi.otta@sungas.org",          # Iju-Otta (sic per sheet)
    "korede.ayomide@sungas.org",    # Osi-Otta
    "adewale.adeoye@sungas.org",    # Sefu
    "olawale.ambali@sungas.org",    # Maba
    "gbenga.olamide@sungas.org",    # Ijoko
    "dayo.olawoyin@sungas.org",     # Ebutte
    "yakubu.hawa@sungas.org",       # Upper Mission
    "macauley.uwagwe@sungas.org",   # Idokpa
    "alozie.faith@sungas.org",      # Ekehuan
    "victor.obi@sungas.org",        # Okhuoromi
    "oriakhi.rachael@sungas.org",   # Idowina
    "favour.iyare@sungas.org",      # Asaba
    "abigail.solomon@sungas.org",   # Reclamation
    "fidelis.akpan@sungas.org",     # Eleme
}

CASHIERS = {
    # Ikeja
    "peace.effiong@sungas.org", "queen.agada@sungas.org", "okewu.queen@sungas.org",
    # Pedro
    "bolanle.ayodele@sungas.org", "bolajoko.abilawon@sungas.org",
    # Bolade
    "blessing.akogwu@sungas.org", "rachael.moses@sungas.org",
    # Aseese
    "funke.baskare@sungas.org", "blessing.amos@sungas.org",
    # Iju-Otta
    "omowunmi.ibiwoye@sungas.org", "abigeal.agbedeyi@sungas.org", "kaosara.kareem@sungas.org",
    # Osi-Otta
    "success.patrick@sungas.org", "funmilayo.akinwalere@sungas.org",
    # Sefu
    "wura.adedeji@sungas.org", "esther.adewale@sungas.org",
    # Maba
    "kafayat.olaiya@sungas.org", "setemi.adesina@sungas.org",
    # Ijoko
    "oluwaseyi.olawole@sungas.org", "omolade.mary@sungas.org",
    # Ebutte
    "seyifunmi.adekoya@sungas.org", "olawunmi.shonubi@sungas.org",
    # Upper Mission
    "victoria.micheal@sungas.org", "sarah.pius@sungas.org",
    "wisdom.ogbevoen@sungas.org", "nimota.sulaimon@sungas.org", "gift.okotogbo@sungas.org",
    # Idokpa
    "deborah.oyiza@sungas.org", "ify.chuks@sungas.org",
    # Ekehuan
    "shima.justine@sungas.org", "gift.odihi@sungas.org",
    # Okhuoromi
    "emmanuella.benjamin@sungas.org", "dominion.roland@sungas.org",
    # Idowina
    "ayomide.joshua@sungas.org", "ruth.ekhowmanye@sungas.org",
    # Asaba
    "endurance.okon@sungas.org", "chikodiri.maduabuchi@sungas.org",
    # Reclamation
    "emmanuel.nnorom@sungas.org", "felicity.agbede@sungas.org", "flourish.akuna@sungas.org",
    # Eleme
    "c.echeazu@sungas.org", "ilami.akari@sungas.org", "abigail.nanee@sungas.org",
}

RETAIL_CUSTOMER_GROUP = "Retail"


# ------------------------------------------------------------------ #
# 3.  Helpers
# ------------------------------------------------------------------ #
def _ensure_role(role_name: str) -> bool:
    """Roles like Sales User / Accounts User must already exist in ERPNext;
    only return True if they really do (do NOT auto-create stock roles)."""
    if frappe.db.exists("Role", role_name):
        return True
    print(f"  [WARN] expected role missing: {role_name!r}")
    return False


def ensure_role_profile(profile_name: str, role_names: list[str]) -> None:
    """Create or refresh a Role Profile to contain exactly the given roles."""
    valid_roles = [r for r in role_names if _ensure_role(r)]
    if not valid_roles:
        print(f"  [SKIP] {profile_name!r}: no valid roles to bundle.")
        return

    if frappe.db.exists("Role Profile", profile_name):
        doc = frappe.get_doc("Role Profile", profile_name)
        existing = {r.role for r in (doc.roles or [])}
        target = set(valid_roles)
        if existing == target:
            print(f"  [skip] Role Profile {profile_name!r} already correct ({len(target)} roles).")
            return
        doc.set("roles", [])
        for r in valid_roles:
            doc.append("roles", {"role": r})
        doc.save(ignore_permissions=True)
        print(f"  [upd ] Role Profile {profile_name!r} now bundles: {', '.join(sorted(target))}")
        return

    doc = frappe.get_doc({
        "doctype": "Role Profile",
        "role_profile": profile_name,
        "roles": [{"role": r} for r in valid_roles],
    })
    doc.insert(ignore_permissions=True)
    print(f"  [new ] Role Profile {profile_name!r} created with: {', '.join(sorted(valid_roles))}")


def assign_role_profile(email: str, profile: str) -> tuple[str, str]:
    """Returns (status, detail). status in {OK, NOOP, MISSING_USER}."""
    if not frappe.db.exists("User", email):
        return "MISSING_USER", "user does not exist"

    user = frappe.get_doc("User", email)
    current = (user.role_profile_name or "").strip()
    child_profiles = {row.role_profile for row in (user.get("role_profiles") or [])}

    if current == profile and child_profiles == {profile}:
        return "NOOP", f"already on {profile!r}"

    user.role_profile_name = profile
    user.set("role_profiles", [])
    user.append("role_profiles", {"role_profile": profile})
    user.save(ignore_permissions=True)
    return "OK", f"{current or '<none>'} -> {profile}"


def ensure_retail_customer_group_perm(email: str) -> str:
    """For cashiers: lock them to the Retail customer group via User Permission.
    Returns one of {added, skip, missing-group}."""
    if not frappe.db.exists("Customer Group", RETAIL_CUSTOMER_GROUP):
        return "missing-group"

    existing = frappe.get_all(
        "User Permission",
        filters={
            "user": email,
            "allow": "Customer Group",
            "for_value": RETAIL_CUSTOMER_GROUP,
        },
        fields=["name"],
        limit=1,
    )
    if existing:
        return "skip"

    doc = frappe.get_doc({
        "doctype": "User Permission",
        "user": email,
        "allow": "Customer Group",
        "for_value": RETAIL_CUSTOMER_GROUP,
        "apply_to_all_doctypes": 1,
    })
    doc.insert(ignore_permissions=True)
    return "added"


# ------------------------------------------------------------------ #
# 4.  Main
# ------------------------------------------------------------------ #
def main():
    print("=" * 78)
    print(" Phase 5.5 -- LPG Role Profiles + cashier/manager assignment")
    print("=" * 78)

    # ---- 4a. Ensure Role Profiles ----
    print("\n[1] Ensure Role Profiles exist with the right bundles:")
    for profile, roles in ROLE_PROFILES.items():
        ensure_role_profile(profile, roles)

    # ---- 4b. Assign profiles ----
    summary = {"updated": 0, "noop": 0, "missing": 0}

    def _assign(group: set[str], profile: str, label: str) -> None:
        print(f"\n--- {label} -> {profile!r} ---")
        for email in sorted(group):
            status, detail = assign_role_profile(email, profile)
            if status == "MISSING_USER":
                summary["missing"] += 1
                print(f"  [MISS] {email}")
                continue
            if status == "OK":
                summary["updated"] += 1
                print(f"  [OK  ] {email:<40} {detail}")
            else:
                summary["noop"] += 1
                print(f"  [skip] {email:<40} {detail}")

    _assign(PLANT_MANAGERS, "LPG Plant Manager", "Plant Managers")
    _assign(CASHIERS,       "LPG POS User",      "Cashiers")

    # ---- 4c. Cashier-only User Permission: Customer Group = Retail ----
    print(f"\n[3] Lock cashiers to Customer Group = {RETAIL_CUSTOMER_GROUP!r}:")
    cust_summary = {"added": 0, "skip": 0, "missing-group": 0, "missing-user": 0}
    for email in sorted(CASHIERS):
        if not frappe.db.exists("User", email):
            cust_summary["missing-user"] += 1
            continue
        status = ensure_retail_customer_group_perm(email)
        cust_summary[status] = cust_summary.get(status, 0) + 1
        if status == "added":
            print(f"  [+   ] {email:<40} -> Customer Group = {RETAIL_CUSTOMER_GROUP}")
    print(
        f"  Cashier User Permissions: added={cust_summary['added']}, "
        f"already-set={cust_summary['skip']}, missing-group={cust_summary['missing-group']}, "
        f"missing-user={cust_summary['missing-user']}"
    )

    frappe.db.commit()

    print("\n" + "=" * 78)
    print(
        f" SUMMARY: profile-assignments updated={summary['updated']}, "
        f"already-correct={summary['noop']}, missing-user={summary['missing']}"
    )
    print("=" * 78)
    print("\nNote: To strictly block cashiers from EDITING existing Customer")
    print("records, a small before_save hook is required (app code change +")
    print("redeploy). User Permission already restricts visibility to the")
    print("Retail group and forces new customers into Retail.")


# Allow `bench execute "exec(open('...').read())"` to locate the functions.
try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
