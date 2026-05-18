"""
Phase-5.5 follow-up: switch all 22 active POS Profiles to submit
POS Invoice (not Sales Invoice), move the 58mm Print Format back to
POS Invoice, and ensure the cashier role has the doctype permissions
to actually write POS Invoice / POS Closing Shift / POS Opening Shift.

Why
---
The cashier smoke test failed with HTTP 403 on POST /api/.../Sales Invoice
because cashiers should not have permission to create Sales Invoices
directly (that's wholesale's job). Switching to POS Invoice mode:

  * Cashiers submit a per-transaction POS Invoice (lean cashier doctype).
  * On POS Closing Shift submit, POS Awesome auto-consolidates them into
    one Sales Invoice per shift via `consolidate_pos_invoices()`.
  * Sales Invoice remains gated to Sales Manager / Accounts roles for
    wholesale / credit deals.

What this script does
---------------------
1. Verifies the `create_pos_invoice_instead_of_sales_invoice` Custom Field
   exists on POS Profile (created by the POS-Awesome patch).
2. Flips it to 1 for every active POS Profile.
3. Moves "Sungas Thermal 58mm" Print Format from Sales Invoice back to
   POS Invoice.
4. Updates the Property Setter so POS Invoice.default_print_format =
   our 58mm template.
5. Adds POS Invoice (read/write/create/submit) doctype permissions to
   the "LPG POS User" Role (in case the role didn't already have them
   through Sales User).
6. Also adds POS Closing Shift / POS Opening Shift permissions so
   cashiers can open/close their shifts.

Run on bench:
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/feat/sungas-customizations/scripts/switch_to_pos_invoice_mode.py" \\
      -o /tmp/switch_to_pos_invoice_mode.py && \\
    bench --site sungasmis.v.frappe.cloud execute \\
      "exec(open('/tmp/switch_to_pos_invoice_mode.py').read())"
"""

from __future__ import annotations

import frappe


PRINT_FORMAT_NAME = "Sungas Thermal 58mm"
POS_INVOICE = "POS Invoice"
TOGGLE_FIELD = "create_pos_invoice_instead_of_sales_invoice"
LPG_POS_ROLE = "LPG POS User"


# Doctypes the cashier needs full create/submit on, beyond what Sales
# User already provides via standard ERPNext role permissions.
POS_DOCTYPES_FOR_ROLE = [
    "POS Invoice",
    "POS Opening Shift",
    "POS Closing Shift",
]


def _ensure_toggle_field_exists() -> bool:
    """The POS Awesome patch `add_pos_invoice_toggle_in_pos_profile.py`
    is what creates this Custom Field. If it hasn't run yet, do it now."""
    name = f"POS Profile-{TOGGLE_FIELD}"
    if frappe.db.exists("Custom Field", name):
        return True
    print(f"  [info] Custom Field '{name}' missing -- creating now.")
    try:
        frappe.get_doc({
            "doctype": "Custom Field",
            "dt": "POS Profile",
            "fieldname": TOGGLE_FIELD,
            "fieldtype": "Check",
            "label": "Create POS Invoice instead of Sales Invoice",
            "insert_after": "posa_show_custom_name_marker_on_print",
        }).insert(ignore_permissions=True)
        return True
    except Exception as exc:
        print(f"  [FATAL] could not create Custom Field: {exc}")
        return False


def _flip_pos_profiles_to_pos_invoice_mode():
    profiles = frappe.get_all("POS Profile", fields=["name", "disabled"])
    flipped = already = disabled = 0
    for p in profiles:
        if p.disabled:
            disabled += 1
            continue
        current = frappe.db.get_value("POS Profile", p.name, TOGGLE_FIELD)
        if current:
            already += 1
            continue
        frappe.db.set_value("POS Profile", p.name, TOGGLE_FIELD, 1)
        flipped += 1
        print(f"    [+] {p.name}")
    return {"flipped": flipped, "already": already, "disabled": disabled, "total": len(profiles)}


def _move_print_format_to_pos_invoice() -> str:
    if not frappe.db.exists("Print Format", PRINT_FORMAT_NAME):
        return f"NOT FOUND: {PRINT_FORMAT_NAME!r} -- run install_pos_print_format.py first"
    pf = frappe.get_doc("Print Format", PRINT_FORMAT_NAME)
    was = pf.doc_type
    if was == POS_INVOICE:
        return f"already on {POS_INVOICE!r}"
    pf.doc_type = POS_INVOICE
    pf.save(ignore_permissions=True)
    return f"MOVED from {was!r} to {POS_INVOICE!r}"


def _set_default_print_format_for_pos_invoice() -> str:
    name = "POS Invoice-main-default_print_format"
    if frappe.db.exists("Property Setter", name):
        ps = frappe.get_doc("Property Setter", name)
        if ps.value == PRINT_FORMAT_NAME:
            return "already set"
        ps.value = PRINT_FORMAT_NAME
        ps.save(ignore_permissions=True)
        return "UPDATED"
    frappe.get_doc({
        "doctype": "Property Setter",
        "doctype_or_field": "DocType",
        "doc_type": POS_INVOICE,
        "property": "default_print_format",
        "property_type": "Data",
        "value": PRINT_FORMAT_NAME,
    }).insert(ignore_permissions=True)
    return "CREATED"


def _wire_pos_profiles_to_use_pf():
    profiles = frappe.get_all("POS Profile", filters={"disabled": 0}, fields=["name"])
    updated = 0
    for p in profiles:
        if frappe.db.get_value("POS Profile", p.name, "print_format") != PRINT_FORMAT_NAME:
            frappe.db.set_value("POS Profile", p.name, "print_format", PRINT_FORMAT_NAME)
            updated += 1
    return updated, len(profiles)


def _ensure_role_doctype_perms():
    """Grant LPG POS User role full create/submit perms on the POS
    doctypes via Custom DocPerm. Idempotent."""
    if not frappe.db.exists("Role", LPG_POS_ROLE):
        return {"error": f"role {LPG_POS_ROLE!r} missing"}

    added = 0
    skipped = 0
    for dt in POS_DOCTYPES_FOR_ROLE:
        if not frappe.db.exists("DocType", dt):
            print(f"    [skip] {dt!r} doctype not installed")
            continue
        existing = frappe.db.exists(
            "Custom DocPerm",
            {"parent": dt, "role": LPG_POS_ROLE, "parenttype": "DocType"},
        )
        if existing:
            skipped += 1
            continue
        frappe.get_doc({
            "doctype": "Custom DocPerm",
            "parent": dt,
            "parenttype": "DocType",
            "parentfield": "permissions",
            "role": LPG_POS_ROLE,
            "permlevel": 0,
            "read": 1,
            "write": 1,
            "create": 1,
            "submit": 1,
            "cancel": 1,
            "amend": 1,
            "print": 1,
            "email": 1,
            "report": 1,
            "export": 1,
        }).insert(ignore_permissions=True)
        added += 1
        print(f"    [+] Custom DocPerm: {LPG_POS_ROLE!r} -> {dt!r}")
    # Custom DocPerms require a clear-cache to take effect immediately.
    frappe.clear_cache()
    return {"added": added, "skipped": skipped}


def main():
    print("=" * 78)
    print(" Switch POS Profiles to POS Invoice mode + receipt + permissions")
    print("=" * 78)

    print("\n[1] Custom Field check (POS Profile.{}): ".format(TOGGLE_FIELD), end="")
    if not _ensure_toggle_field_exists():
        return
    print("OK")

    print("\n[2] Flip POS Profiles to POS Invoice mode:")
    s = _flip_pos_profiles_to_pos_invoice_mode()
    print(f"    summary: flipped={s['flipped']}  already-on={s['already']}  "
          f"disabled={s['disabled']}  total={s['total']}")

    print("\n[3] Move Print Format -> POS Invoice doctype: ", end="")
    print(_move_print_format_to_pos_invoice())

    print("\n[4] POS Invoice default_print_format Property Setter: ", end="")
    print(_set_default_print_format_for_pos_invoice())

    print("\n[5] Re-wire POS Profile.print_format pointer: ", end="")
    upd, tot = _wire_pos_profiles_to_use_pf()
    print(f"updated {upd} of {tot}")

    print(f"\n[6] Grant {LPG_POS_ROLE!r} permissions on POS doctypes:")
    r = _ensure_role_doctype_perms()
    if "error" in r:
        print(f"    {r['error']}")
    else:
        print(f"    summary: added={r['added']}, already-had={r['skipped']}")

    frappe.db.commit()
    print("\n" + "=" * 78)
    print(" DONE. Re-test the cashier smoke flow now:")
    print("   1. Logout, login as peace.effiong@sungas.org / SungasTest@2026")
    print("   2. Open POS Awesome -> Create Opening Entry -> Ikeja")
    print("   3. Ring 1kg LPG Refill -> tender cash -> Submit")
    print("   4. POS Invoice (not Sales Invoice) should be created.")
    print("   5. 58mm receipt should print the lean Sungas template.")
    print("=" * 78)


try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
