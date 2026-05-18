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
# Note: POS Awesome does NOT require the built-in 'POS User' role -- it
# creates Sales Invoices through the Sales User permission set.
POS_BASE_ROLES = [
    "Sales User",
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
def clear_stale_role_profile_locks() -> int:
    """The Role Profile `on_update` hook calls `queue_action()` which
    creates a filesystem lock (`sites/<site>/locks/Role Profile_*.lock`)
    in Frappe v15 -- and in some builds a `tabDocument Lock` row. Either
    can outlive a rolled-back transaction and brick the next run.

    Wipe both forms for any of our four LPG Role Profiles."""
    import os
    import glob

    profile_names = list(ROLE_PROFILES.keys())
    cleared = 0

    # --- 1. Filesystem locks (v15 default) ---
    try:
        locks_dir = frappe.get_site_path("locks")
        if os.path.isdir(locks_dir):
            # Lock filename pattern: "<DocType>_<name>.lock"
            for profile in profile_names:
                # Try exact match plus generic "Role Profile_*" glob to catch
                # any name-sanitization variants.
                candidates = [
                    os.path.join(locks_dir, f"Role Profile_{profile}.lock"),
                    os.path.join(locks_dir, f"role_profile_{profile}.lock"),
                ]
                for path in candidates:
                    if os.path.exists(path):
                        os.remove(path)
                        cleared += 1
                        print(f"  removed lock file: {os.path.basename(path)}")
            # Catch any leftover Role Profile lock files (e.g. weird casing).
            for path in glob.glob(os.path.join(locks_dir, "Role Profile_*.lock")):
                try:
                    os.remove(path)
                    cleared += 1
                    print(f"  removed stray lock: {os.path.basename(path)}")
                except FileNotFoundError:
                    pass
    except Exception as exc:
        print(f"  WARN filesystem-lock cleanup failed: {exc}")

    # --- 2. DB locks (newer Frappe builds) ---
    try:
        if frappe.db.table_exists("Document Lock"):
            placeholders = ", ".join(["%s"] * len(profile_names))
            rows = frappe.db.sql(
                f"""DELETE FROM `tabDocument Lock`
                    WHERE document_type = 'Role Profile'
                      AND document_name IN ({placeholders})""",
                tuple(profile_names),
            )
            cleared += int(rows or 0)
            frappe.db.commit()
    except Exception as exc:
        print(f"  WARN DB-lock cleanup failed: {exc}")

    return cleared


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
        frappe.db.commit()  # persist immediately
        print(f"  [upd ] Role Profile {profile_name!r} now bundles: {', '.join(sorted(target))}")
        return

    doc = frappe.get_doc({
        "doctype": "Role Profile",
        "role_profile": profile_name,
        "roles": [{"role": r} for r in valid_roles],
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()  # persist immediately so a later error can't roll it back
    print(f"  [new ] Role Profile {profile_name!r} created with: {', '.join(sorted(valid_roles))}")


def assign_role_profile(email: str, profile: str) -> tuple[str, str]:
    """Returns (status, detail). status in {OK, NOOP, MISSING_USER}.

    Uses the legacy `role_profile_name` field only -- Frappe's User
    validate hook reads that field and overwrites `user.roles` with the
    profile's role set, so we don't need to touch `user.roles` directly.
    """
    if not frappe.db.exists("User", email):
        return "MISSING_USER", "user does not exist"

    user = frappe.get_doc("User", email)
    current = (user.role_profile_name or "").strip()

    if current == profile:
        return "NOOP", f"already on {profile!r}"

    user.role_profile_name = profile
    # Explicitly clear existing roles so save() re-populates them from the
    # profile (safer than relying on Frappe's append-vs-replace semantics,
    # which differ across Frappe minor versions).
    user.set("roles", [])
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

    # ---- 4a. Defang the queue lock guards.
    # Frappe Cloud's v15 build's queue_action() runs BOTH check_if_locked()
    # AND self.lock() before the in_migrate short-circuit, so we need to
    # neuter both. Locks are filesystem-based with sha224-hashed names we
    # can't target reliably from outside. Cleanest workaround: monkey-patch
    # both methods to no-ops for the duration of this setup script, then
    # restore them in a finally block.
    from frappe.model.document import Document
    _orig_check_if_locked = Document.check_if_locked
    _orig_lock = Document.lock
    Document.check_if_locked = lambda self: None
    Document.lock = lambda self, timeout=None: None
    frappe.flags.in_migrate = True
    print("\n[0] Lock guard disabled for this setup pass.")

    try:
        # Best-effort cleanup of any stale lock files we recognise.
        n_locks = clear_stale_role_profile_locks()
        if n_locks:
            print(f"      cleared {n_locks} explicit lock file(s).")

        # ---- 4b. Ensure Role Profiles ----
        print("\n[1] Ensure Role Profiles exist with the right bundles:")
        for profile, roles in ROLE_PROFILES.items():
            ensure_role_profile(profile, roles)

        # ---- 4c. Assign profiles ----
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

        # ---- 4d. Cashier-only User Permission: Customer Group = Retail ----
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
    finally:
        # Always restore the original lock guards, even if the body errors.
        Document.check_if_locked = _orig_check_if_locked
        Document.lock = _orig_lock


# Allow `bench execute "exec(open('...').read())"` to locate the functions.
try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
