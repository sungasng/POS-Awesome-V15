"""
Phase-5.5: assign Role Profiles to every Plant Manager and Cashier listed
in the OUTLET_CASHIER_MAP, so they can create/submit POS Invoices.

Role Profile mapping (Role Profiles already exist in the site):
  - Cashiers       -> "LPG POS User"
  - Plant Managers -> "LPG Plant Manager"

LPG Head of Sales / LPG Head of Finance assignments are handled
separately (already configured on the site).

Behaviour:
  - Overwrites any existing Role Profile on each user (clean slate).
  - Sets both the legacy `role_profile_name` and the v15 `role_profiles`
    child table so Frappe re-syncs the user's roles from the profile.

Run on bench:
    curl -fsSL https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/feat/sungas-customizations/scripts/assign_cashier_roles.py \
      -o /tmp/assign_cashier_roles.py && \
    bench --site sungasmis.v.frappe.cloud execute \
      "exec(open('/tmp/assign_cashier_roles.py').read())"
"""

from __future__ import annotations

import frappe


CASHIER_PROFILE = "LPG POS User"
MANAGER_PROFILE = "LPG Plant Manager"

# Plant managers (first email per outlet in the spreadsheet).
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

# Cashiers (everyone else in the outlet roster).
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


def _profile_exists(profile: str) -> bool:
    return bool(frappe.db.exists("Role Profile", profile))


def assign_role_profile(email: str, profile: str) -> tuple[str, str]:
    """Returns (status, detail). status in {OK, NOOP, MISSING_USER}."""
    if not frappe.db.exists("User", email):
        return "MISSING_USER", "user does not exist"

    user = frappe.get_doc("User", email)
    current = (user.role_profile_name or "").strip()

    # If already correctly assigned (both legacy and child-table), no-op.
    child_profiles = {row.role_profile for row in (user.get("role_profiles") or [])}
    if current == profile and child_profiles == {profile}:
        return "NOOP", f"already on {profile!r}"

    # Overwrite: clear any existing role profiles, then assign the target one.
    user.role_profile_name = profile
    user.set("role_profiles", [])
    user.append("role_profiles", {"role_profile": profile})

    # Saving the user with role_profile_name set causes Frappe to re-sync
    # the user's `roles` child table from the Role Profile definition.
    user.save(ignore_permissions=True)

    return "OK", f"{current or '<none>'} -> {profile}"


def main():
    print("=" * 78)
    print(" Assign Role Profiles (overwrite) to plant managers + cashiers")
    print("=" * 78)

    for profile in (CASHIER_PROFILE, MANAGER_PROFILE):
        if not _profile_exists(profile):
            print(f"  [FATAL] Role Profile {profile!r} not found - aborting.")
            return

    summary = {"updated": 0, "noop": 0, "missing": 0}

    print(f"\n--- Plant Managers -> {MANAGER_PROFILE!r} ---")
    for email in sorted(PLANT_MANAGERS):
        status, detail = assign_role_profile(email, MANAGER_PROFILE)
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

    print(f"\n--- Cashiers -> {CASHIER_PROFILE!r} ---")
    for email in sorted(CASHIERS):
        status, detail = assign_role_profile(email, CASHIER_PROFILE)
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

    frappe.db.commit()
    print(
        f"\n Summary: updated={summary['updated']}, "
        f"already-correct={summary['noop']}, missing-user={summary['missing']}"
    )


# Allow `bench execute "exec(open('...').read())"` to find module-level defs.
try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
