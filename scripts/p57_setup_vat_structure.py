"""p57_setup_vat_structure.py
==============================
Create Item Tax Templates per Item Group and wire them up so every POS
Invoice carries an explicit VAT line — including the FIRS-compliant 0%
line for LPG and LPG accessories.

Why explicit 0% lines: FIRS expects receipts to show VAT as a separate
total even when the rate is zero, so audit can prove the exemption was
applied (rather than that VAT was simply omitted).

Defaults (edit ITEM_GROUP_RATES at top to change):
  LPG-Cylinders   -> 0% (LPG-related equipment, FG waiver)
  LPG             -> 0% (the gas itself)
  Gas Cookers     -> 0% (LPG-related equipment, FG waiver)
  Accessories     -> 0% (LPG-related accessories, FG waiver)
  default fallback-> 7.5% (Nigeria standard VAT, for future non-LPG items)

The script:
  1. Confirms/creates a single Sales Taxes and Charges Template
     "Nigeria VAT (Item Tax Driven)" that has ONE row pointing at the
     output VAT account with charge_type='On Net Total' rate=0.
     Item Tax Templates per group OVERRIDE this rate at invoice line level,
     so the same template handles all item groups correctly.
  2. Creates one Item Tax Template per ITEM_GROUP_RATES entry.
  3. Attaches each template to its Item Group via the tabItem Tax child table.
  4. Sets the new template as the default Sales Tax template on every
     enabled POS Profile.

Idempotent: re-running picks up new groups, doesn't duplicate templates.

Run:
  bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/p57_vat_setup.py').read())"
"""
import frappe  # type: ignore # noqa: F401

# === EDIT THESE TO MATCH YOUR CoA AFTER RUNNING THE AUDIT =====================
# The audit script lists existing VAT accounts. Pick the OUTPUT VAT one
# (root_type=Liability, account_type=Tax). Leaf account, NOT a group.
COMPANY = "SUNGAS COMPANY LIMITED"  # confirmed from UI on 2026-06-03
OUTPUT_VAT_ACCOUNT = "VAT - SCL"    # confirmed via p57_audit_vat_setup 2026-06-05

# Per-item-group VAT rates. Add/edit freely. Groups not listed here will
# use FALLBACK_RATE.
ITEM_GROUP_RATES = {
    "LPG-Cylinders":  0.0,
    "LPG":            0.0,
    "Gas Cookers":    0.0,
    "Accessories":    0.0,
}
FALLBACK_RATE = 7.5  # Nigeria standard VAT for non-LPG items (future-proof)

# Names used for the templates we create
SALES_TAX_TEMPLATE_NAME = "Nigeria VAT (Item Tax Driven)"
ITEM_TAX_TEMPLATE_PREFIX = "Nigeria VAT"  # produces e.g. "Nigeria VAT 0% - LPG"
# =============================================================================


def _ensure_sales_tax_template():
    """Single sales-tax template referenced by every POS Profile. The actual
    per-item rate comes from Item Tax Template overrides — this template only
    needs to declare the VAT account at rate 0; the line-level template wins.
    """
    name = SALES_TAX_TEMPLATE_NAME
    if frappe.db.exists("Sales Taxes and Charges Template", name):
        print(f"  = Sales Taxes and Charges Template '{name}' already exists.")
        return name

    doc = frappe.get_doc({
        "doctype": "Sales Taxes and Charges Template",
        "title": name,
        "company": COMPANY,
        "is_default": 0,
        "disabled": 0,
        "taxes": [{
            "charge_type": "On Net Total",
            "account_head": OUTPUT_VAT_ACCOUNT,
            "rate": 0,
            "description": "VAT (rate determined per item by Item Tax Template)",
        }],
    })
    doc.insert(ignore_permissions=True)
    print(f"  + Created Sales Taxes and Charges Template: {name}")
    return name


def _item_tax_template_name(rate: float, group: str) -> str:
    rate_label = "0%" if rate == 0 else f"{rate:g}%"
    return f"{ITEM_TAX_TEMPLATE_PREFIX} {rate_label} - {group}"


def _ensure_item_tax_template(rate: float, group: str) -> str:
    name = _item_tax_template_name(rate, group)
    if frappe.db.exists("Item Tax Template", name):
        return name
    doc = frappe.get_doc({
        "doctype": "Item Tax Template",
        "title": name,
        "company": COMPANY,
        "taxes": [{
            "tax_type": OUTPUT_VAT_ACCOUNT,
            "tax_rate": rate,
        }],
    })
    doc.insert(ignore_permissions=True)
    print(f"  + Created Item Tax Template: {name}")
    return name


def _attach_template_to_item_group(template_name: str, group: str):
    if not frappe.db.exists("Item Group", group):
        print(f"  ! Item Group '{group}' not found, skipping.")
        return
    grp = frappe.get_doc("Item Group", group)
    for row in (grp.taxes or []):
        if row.item_tax_template == template_name:
            return  # already attached
    grp.append("taxes", {
        "item_tax_template": template_name,
        "valid_from": None,
        "maximum_net_rate": 0,
        "minimum_net_rate": 0,
    })
    grp.save(ignore_permissions=True)
    print(f"  + Attached '{template_name}' to Item Group '{group}'")


def _set_default_tax_on_pos_profiles(template_name: str):
    profiles = frappe.get_all(
        "POS Profile",
        filters={"company": COMPANY, "disabled": 0},
        pluck="name",
        order_by="name",
    )
    changed = 0
    for pname in profiles:
        cur = frappe.db.get_value("POS Profile", pname, "taxes_and_charges")
        if cur == template_name:
            continue
        frappe.db.set_value(
            "POS Profile", pname, "taxes_and_charges", template_name, update_modified=True
        )
        changed += 1
        print(f"  + POS Profile '{pname}' taxes_and_charges: '{cur}' -> '{template_name}'")
    if changed == 0:
        print(f"  = All {len(profiles)} POS Profiles already use '{template_name}'.")


def main():
    if not frappe.db.exists("Account", OUTPUT_VAT_ACCOUNT):
        print(f"\n  ! Output VAT account '{OUTPUT_VAT_ACCOUNT}' does not exist.")
        print("    Edit OUTPUT_VAT_ACCOUNT at the top of this script after")
        print("    running p57_audit_vat_setup.py to find the right account name.")
        print("    If no VAT account exists yet, create one in the CoA under")
        print("    'Duties and Taxes - SCL' (Liability) with account_type='Tax'.")
        return

    print("\n=== Step 1: Sales Taxes and Charges Template ===")
    sales_template = _ensure_sales_tax_template()

    print("\n=== Step 2: Item Tax Templates per Item Group ===")
    group_to_template = {}
    for group, rate in ITEM_GROUP_RATES.items():
        if not frappe.db.exists("Item Group", group):
            print(f"  ! Item Group '{group}' not found, skipping.")
            continue
        tmpl = _ensure_item_tax_template(rate, group)
        group_to_template[group] = tmpl

    # Also ensure the FALLBACK_RATE template exists, attach later if you add
    # non-LPG item groups
    fallback_name = _ensure_item_tax_template(FALLBACK_RATE, "Default")
    print(f"  (fallback {FALLBACK_RATE}% template available: '{fallback_name}')")

    # Commit so the templates are visible to the link validator in Step 3.
    # Without this commit, _attach_template_to_item_group's grp.save() raises
    # LinkValidationError because the just-created templates aren't yet in
    # the row that Frappe queries for link existence checks.
    frappe.db.commit()

    print("\n=== Step 3: Attach Item Tax Templates to Item Groups ===")
    for group, tmpl in group_to_template.items():
        _attach_template_to_item_group(tmpl, group)

    print("\n=== Step 4: Set default sales tax template on POS Profiles ===")
    _set_default_tax_on_pos_profiles(sales_template)

    frappe.db.commit()
    print("\n+ VAT structure set up. Next invoice should show a VAT line at 0%.\n")


# _BENCH_EXEC_FIX: bench execute "exec(...)" runs scripts with separate
# globals/locals dicts, so module-level functions can't see other module-level
# helpers. Copying locals -> globals before invoking main() fixes the scope.
globals().update(locals())
main()
