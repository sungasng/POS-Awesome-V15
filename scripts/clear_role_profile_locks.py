"""
Diagnostic + cleanup for stuck Document Lock rows on Role Profiles.

Inspects everything Frappe knows about locks on our four LPG Role
Profiles, then wipes them (DB rows + any filesystem .lock files).
Safe to run multiple times.

Run on bench:
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/feat/sungas-customizations/scripts/clear_role_profile_locks.py?$(date +%s)" \
      -o /tmp/clear_role_profile_locks.py && \
    bench --site sungasmis.v.frappe.cloud execute \
      "exec(open('/tmp/clear_role_profile_locks.py').read())"
"""

from __future__ import annotations

import os
import glob

import frappe


TARGET_PROFILES = [
    "LPG POS User",
    "LPG Plant Manager",
    "LPG Head of Sales",
    "LPG Head of Finance",
]


def main():
    print("=" * 78)
    print(" Role Profile lock diagnostic + cleanup")
    print("=" * 78)

    # ---- 1. Document Lock doctype? ----
    has_doctype = frappe.db.exists("DocType", "Document Lock")
    print(f"\n[1] Document Lock doctype exists: {bool(has_doctype)}")

    # ---- 2. Document Lock rows for Role Profile ----
    print("\n[2] Document Lock rows for doctype = 'Role Profile':")
    try:
        rows = frappe.get_all(
            "Document Lock",
            filters={"document_type": "Role Profile"},
            fields=["name", "document_name", "modified"],
            ignore_permissions=True,
        )
    except Exception as exc:
        rows = []
        print(f"    (could not query Document Lock: {exc})")
    if not rows:
        print("    (none)")
    for r in rows:
        print(f"    - lock={r.name!r}  doc={r.document_name!r}  modified={r.modified}")

    # ---- 3. Filesystem locks ----
    print("\n[3] Filesystem lock files under sites/<site>/locks/:")
    locks_dir = frappe.get_site_path("locks")
    if os.path.isdir(locks_dir):
        found = sorted(os.listdir(locks_dir))
        if not found:
            print("    (none)")
        for fn in found:
            print(f"    - {fn}")
    else:
        print(f"    locks dir not found at {locks_dir}")

    # ---- 4. Wipe everything we found ----
    print("\n[4] Cleaning up:")
    db_deleted = 0
    for r in rows:
        try:
            frappe.db.delete("Document Lock", r.name)
            db_deleted += 1
            print(f"    [DB ] deleted lock row {r.name!r} for {r.document_name!r}")
        except Exception as exc:
            print(f"    [WARN] could not delete row {r.name!r}: {exc}")

    # Also blanket-delete by filter (catches any rows we couldn't enumerate).
    try:
        frappe.db.delete("Document Lock", {"document_type": "Role Profile"})
    except Exception:
        pass

    frappe.db.commit()

    fs_deleted = 0
    if os.path.isdir(locks_dir):
        patterns = [
            "Role Profile_*.lock",
            "role_profile_*.lock",
            "role-profile_*.lock",
        ]
        for pat in patterns:
            for path in glob.glob(os.path.join(locks_dir, pat)):
                try:
                    os.remove(path)
                    fs_deleted += 1
                    print(f"    [FS ] removed {os.path.basename(path)}")
                except FileNotFoundError:
                    pass

    print(f"\n SUMMARY: db_locks_deleted={db_deleted}, fs_locks_deleted={fs_deleted}")

    # ---- 5. Re-probe to confirm clean ----
    print("\n[5] Post-cleanup probe:")
    try:
        leftover = frappe.get_all(
            "Document Lock",
            filters={"document_type": "Role Profile"},
            fields=["name"],
        )
    except Exception:
        leftover = []
    print(f"    remaining DB locks on Role Profile: {len(leftover)}")
    if os.path.isdir(locks_dir):
        leftover_fs = [
            f for f in os.listdir(locks_dir)
            if f.lower().startswith("role profile_") or f.lower().startswith("role_profile_")
        ]
        print(f"    remaining FS lock files: {len(leftover_fs)}  -> {leftover_fs}")


try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
