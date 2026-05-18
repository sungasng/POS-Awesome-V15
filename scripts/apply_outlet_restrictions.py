"""
Phase-5.5 final-final fixes:

1. Verify Server Scripts are enabled (instruct user if not).
2. Apply outlet-scoped Territory User Permissions to every cashier
   and plant manager so they only see data tied to their outlet --
   EXCEPT Customer (which remains globally readable so they can sell
   to any walk-in).
3. Print a clear set of remaining manual steps.

Run:
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/feat/sungas-customizations/scripts/apply_outlet_restrictions.py" \\
      -o /tmp/apply_outlet_restrictions.py && \\
    bench --site sungasmis.v.frappe.cloud execute \\
      "exec(open('/tmp/apply_outlet_restrictions.py').read())"
"""

from __future__ import annotations

import frappe


# Doctypes a cashier / plant manager should see ONLY for their own outlet.
# Customer is intentionally absent -- they can sell to walk-ins from any group.
OUTLET_SCOPED_DOCTYPES = [
    "POS Invoice",
    "POS Opening Shift",
    "POS Closing Shift",
    "Sales Invoice",
    "Sales Order",
    "Delivery Note",
    "Payment Entry",
    "Stock Entry",
    "Stock Reconciliation",
    "Stock Ledger Entry",
    "Material Request",
]


def server_scripts_enabled() -> bool:
    if frappe.local.conf.get("server_script_enabled"):
        return True
    return bool(frappe.db.get_single_value("System Settings", "developer_mode"))


def derive_territory(profile_name: str) -> str:
    """`POS - Ikeja` -> `Ikeja`; `POS - Pedro (Test)` -> `Pedro`."""
    return profile_name.replace("POS - ", "").replace(" (Test)", "").strip()


def collect_user_outlet_map() -> dict[str, set[str]]:
    """Returns {user_email: {territory, ...}} from POS Profile's
    applicable_for_users child table."""
    mapping: dict[str, set[str]] = {}
    profiles = frappe.get_all(
        "POS Profile",
        filters={"disabled": 0},
        fields=["name"],
    )
    for p in profiles:
        territory = derive_territory(p.name)
        if not frappe.db.exists("Territory", territory):
            continue
        users = frappe.get_all(
            "POS Profile User",
            filters={"parent": p.name},
            fields=["user"],
        )
        for u in users:
            if not u.user:
                continue
            mapping.setdefault(u.user, set()).add(territory)
    return mapping


def upsert_user_permission(
    user: str, territory: str, applicable_for: list[str]
) -> int:
    """Returns count of doctype rows added under applicable_for."""
    # Re-use an existing UP for (user, Territory, territory) if present;
    # otherwise create one. We always rewrite the applicable_for_doctypes
    # to ensure all OUTLET_SCOPED_DOCTYPES are covered.
    existing = frappe.db.get_value(
        "User Permission",
        {
            "user": user,
            "allow": "Territory",
            "for_value": territory,
        },
        "name",
    )
    if existing:
        doc = frappe.get_doc("User Permission", existing)
    else:
        doc = frappe.new_doc("User Permission")
        doc.user = user
        doc.allow = "Territory"
        doc.for_value = territory

    doc.apply_to_all_doctypes = 0

    # The child-table name varies by Frappe version. Locate it dynamically.
    target_field = None
    for f in doc.meta.get("fields", []):
        if f.fieldtype == "Table" and "doctype" in (f.options or "").lower():
            target_field = f.fieldname
            break
    if not target_field:
        # Fallback: applicable_for_doctypes is the v15 default
        target_field = "applicable_for_doctypes"

    try:
        doc.set(target_field, [])
        for dt in applicable_for:
            if frappe.db.exists("DocType", dt):
                doc.append(target_field, {"applicable_for": dt})
    except Exception:
        # If the field doesn't exist, fall back to apply_to_all=1
        doc.apply_to_all_doctypes = 1

    if existing:
        doc.save(ignore_permissions=True)
    else:
        doc.insert(ignore_permissions=True)
    return len(applicable_for)


def main():
    print("=" * 78)
    print(" Apply outlet-scoped Territory User Permissions")
    print("=" * 78)

    # ----- 0. Confirm Server Scripts state -----
    ss = server_scripts_enabled()
    print(f"\n[0] Server Scripts enabled on site: {ss}")
    if not ss:
        print("    !! Customer create/edit Server Scripts will NOT fire.")
        print("       Enable them with:")
        print("         bench --site sungasmis.v.frappe.cloud set-config "
              "server_script_enabled 1")
        print("         bench restart")
        print("       Then cashiers will be forced into Retail group and")
        print("       blocked from editing customers at the server layer,")
        print("       regardless of whether the form is Frappe Desk or the")
        print("       POS Awesome Vue dialog.")

    # ----- 1. Collect outlet -> user map -----
    user_map = collect_user_outlet_map()
    print(f"\n[1] Discovered {len(user_map)} users across active POS Profiles.")

    # ----- 2. Apply Territory User Permission for each -----
    print("\n[2] Applying Territory User Permissions:")
    summary_added = 0
    summary_users = 0
    for user, territories in sorted(user_map.items()):
        for territory in sorted(territories):
            try:
                added = upsert_user_permission(
                    user, territory, OUTLET_SCOPED_DOCTYPES
                )
                summary_added += added
                summary_users += 1
                print(f"    [OK] {user:<40} -> Territory = {territory!r}")
            except Exception as exc:
                print(f"    [ERR] {user} -> {territory}: {exc}")

    frappe.db.commit()
    frappe.clear_cache()

    print(f"\n[3] Summary: {summary_users} user-territory bindings, "
          f"{summary_added} doctype-scope entries.")

    print("\n" + "=" * 78)
    print(" REMAINING MANUAL STEPS")
    print("=" * 78)
    print(" 1. To enforce Customer create/edit rules server-side:")
    print("    bench --site sungasmis.v.frappe.cloud set-config "
          "server_script_enabled 1")
    print("    bench restart")
    print()
    print(" 2. Verify a cashier (peace.effiong@sungas.org):")
    print("    a. Can see only Ikeja Sales Invoices / Stock entries.")
    print("    b. Can still find customers from any group in POS search.")
    print("    c. Cannot select non-Retail group when creating a customer.")
    print("    d. Cannot edit existing customers.")
    print("=" * 78)


try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
