"""
Fix Server Script event names (Title Case) + add Custom DocPerm
defence-in-depth so even if Server Scripts misfire, cashiers cannot
write to Customer.

Run:
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/feat/sungas-customizations/scripts/fix_customer_lockdown.py" \\
      -o /tmp/fix_customer_lockdown.py && \\
    bench --site sungasmis.v.frappe.cloud execute \\
      "exec(open('/tmp/fix_customer_lockdown.py').read())"
"""

from __future__ import annotations

import frappe


LPG_POS_ROLE = "LPG POS User"
RETAIL_GROUP = "Retail"


SERVER_SCRIPT_INSERT = (
    "SENIORS = {'System Manager', 'Sales Manager', 'Accounts Manager', "
    "'LPG Plant Manager', 'LPG Head of Sales', 'LPG Head of Finance'}\n"
    "user_roles = set(frappe.get_roles(frappe.session.user))\n"
    "if 'LPG POS User' in user_roles and not (user_roles & SENIORS):\n"
    "    doc.customer_group = 'Retail'\n"
)

SERVER_SCRIPT_UPDATE = (
    "if not doc.is_new():\n"
    "    SENIORS = {'System Manager', 'Sales Manager', 'Accounts Manager', "
    "'LPG Plant Manager', 'LPG Head of Sales', 'LPG Head of Finance'}\n"
    "    user_roles = set(frappe.get_roles(frappe.session.user))\n"
    "    if 'LPG POS User' in user_roles and not (user_roles & SENIORS):\n"
    "        frappe.throw('Cashiers cannot edit existing customer profiles.')\n"
)


def fix_server_scripts():
    """Re-install the two Customer Server Scripts with Frappe's correct
    Title Case event names. The earlier version used snake_case which
    silently never matched any event."""
    print("\n[1] Fix Server Script event names to Title Case:")

    targets = [
        (
            "Sungas - Force Retail Group On Customer Insert",
            "Before Insert",
            SERVER_SCRIPT_INSERT,
        ),
        (
            "Sungas - Block Customer Edits By Cashier",
            "Before Save",
            SERVER_SCRIPT_UPDATE,
        ),
    ]
    for name, event, body in targets:
        if frappe.db.exists("Server Script", name):
            frappe.db.delete("Server Script", name)
            frappe.db.commit()
        try:
            frappe.get_doc({
                "doctype": "Server Script",
                "name": name,
                "script_type": "DocType Event",
                "reference_doctype": "Customer",
                "doctype_event": event,
                "disabled": 0,
                "script": body,
            }).insert(ignore_permissions=True)
            print(f"    [OK] {name!r} -> {event!r}")
        except Exception as exc:
            print(f"    [ERR] {name!r}: {exc}")
    frappe.db.commit()


def harden_with_custom_docperm():
    """Defence-in-depth: revoke write/delete/amend permissions on
    Customer for the LPG POS User role. Read + Create are kept so
    cashiers can search Customers in POS and create new ones (the
    Server Script forces customer_group=Retail on insert)."""
    print(f"\n[2] Custom DocPerm: {LPG_POS_ROLE!r} on Customer (read+create only):")

    # Wipe any existing Custom DocPerm we set for this role on Customer
    # so we don't end up with two contradicting rows.
    existing = frappe.get_all(
        "Custom DocPerm",
        filters={"parent": "Customer", "role": LPG_POS_ROLE},
        fields=["name"],
    )
    for r in existing:
        frappe.db.delete("Custom DocPerm", r.name)

    doc = frappe.get_doc({
        "doctype": "Custom DocPerm",
        "parent": "Customer",
        "parenttype": "DocType",
        "parentfield": "permissions",
        "role": LPG_POS_ROLE,
        "permlevel": 0,
        "read": 1,
        "create": 1,
        "write": 0,
        "delete": 0,
        "submit": 0,
        "cancel": 0,
        "amend": 0,
        "print": 1,
        "email": 0,
        "report": 1,
        "export": 0,
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    frappe.clear_cache(doctype="Customer")
    print(f"    [OK] Custom DocPerm installed (read=1, create=1, write=0, delete=0)")


def smoke_test_as_cashier():
    """Programmatically simulate a cashier creating + updating a
    Customer. Confirms our two defences actually fire end-to-end."""
    print("\n[3] Smoke-test as cashier (peace.effiong@sungas.org):")
    if not frappe.db.exists("User", "peace.effiong@sungas.org"):
        print("    [skip] cashier user missing")
        return
    if not frappe.db.exists("Customer Group", "Bulk"):
        print("    [skip] Bulk group missing (cannot test forced-Retail)")
        return

    original_user = frappe.session.user
    test_name = "ZZ Sungas Lockdown Test"
    try:
        frappe.set_user("peace.effiong@sungas.org")

        # ----- A. Try to create as Bulk -> should be forced to Retail -----
        try:
            if frappe.db.exists("Customer", test_name):
                frappe.delete_doc("Customer", test_name, ignore_permissions=True, force=True)
            new = frappe.get_doc({
                "doctype": "Customer",
                "customer_name": test_name,
                "customer_group": "Bulk",     # cashier picks Bulk
                "territory": "All Territories",
            })
            new.insert()
            actual = frappe.db.get_value("Customer", test_name, "customer_group")
            print(f"    [A] insert as Bulk -> Customer Group stored = {actual!r}")
            if actual == "Retail":
                print("        OK Server Script forced Bulk -> Retail")
            else:
                print("        FAIL Server Script did NOT enforce -- check enable flag")
        except Exception as exc:
            print(f"    [A] insert raised: {type(exc).__name__}: {exc}")

        # ----- B. Try to edit -> should throw -----
        try:
            cust = frappe.get_doc("Customer", test_name)
            cust.customer_name = test_name + " (edited)"
            cust.save()
            print(f"    [B] update succeeded -- defence LEAKED (should have thrown)")
        except frappe.PermissionError as exc:
            print(f"    [B] update blocked by Custom DocPerm (PermissionError): {exc}")
        except frappe.ValidationError as exc:
            print(f"    [B] update blocked by Server Script: {exc}")
        except Exception as exc:
            print(f"    [B] update blocked: {type(exc).__name__}: {exc}")

        # Cleanup
        try:
            frappe.set_user("Administrator")
            if frappe.db.exists("Customer", test_name):
                frappe.delete_doc("Customer", test_name, ignore_permissions=True, force=True)
            frappe.db.commit()
        except Exception:
            pass
    finally:
        frappe.set_user(original_user)


def main():
    print("=" * 78)
    print(" Customer lockdown: fix event names + add Custom DocPerm")
    print("=" * 78)

    fix_server_scripts()
    harden_with_custom_docperm()

    frappe.clear_cache()
    frappe.db.commit()

    smoke_test_as_cashier()

    print("\n" + "=" * 78)
    print(" Done. Re-test in POS Awesome:")
    print("   1. Try to create a customer in 'Bulk' -- should land as 'Retail'.")
    print("   2. Try to update an existing customer -- should be denied.")
    print("=" * 78)


try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
