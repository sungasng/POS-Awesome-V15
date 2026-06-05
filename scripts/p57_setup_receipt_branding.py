"""p57_setup_receipt_branding.py
=================================
Add per-POS-Profile branding overrides so Itele can print as "Bobo Gas"
(separate legal entity, separate TIN) while every other outlet prints
as "Sungas Company Limited" -- without forcing us to create a second
ERPNext Company.

Strategy:
  - Three new Custom Fields on POS Profile:
      * custom_legal_entity_name    (Data, default "SUNGAS COMPANY LIMITED")
      * custom_legal_entity_tin     (Data, default "00201561-0001")
      * custom_legal_entity_address (Small Text, default "1, Obasa Road, Ikeja, Lagos")
  - Backfill every enabled POS Profile with the Sungas defaults.
  - Override POS - Itele with Bobo Gas values.

The receipt print format reads these custom fields via Jinja
({{ doc.pos_profile_doc.custom_legal_entity_name }}) so changing the
profile flips the printed legal entity without code changes.

Run:
  bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/p57_brand.py').read())"

Re-runnable: idempotent on the custom field creation; profile updates only
overwrite explicit defaults (so any manual per-outlet edits survive).
"""
import frappe  # type: ignore # noqa: F401

# === EDIT THESE BEFORE RUNNING ==============================================
SUNGAS_DEFAULTS = {
    "custom_legal_entity_name":    "SUNGAS COMPANY LIMITED",
    "custom_legal_entity_tin":     "00201561-0001",
    "custom_legal_entity_address": "1, Obasa Road, Ikeja, Lagos",
}

# Per-profile overrides (only Itele rebranded for now)
PROFILE_OVERRIDES = {
    "POS - Itele": {
        "custom_legal_entity_name":    "BOBO GAS",
        "custom_legal_entity_tin":     "2501110131157",
        # Address: defaults to existing branch address on the POS Profile, but
        # if you want a different "registered office" address printed on Bobo Gas
        # receipts, set it here. Leaving as None keeps the Sungas default.
        "custom_legal_entity_address": None,  # falls back to Sungas default
    },
}

CUSTOM_FIELDS_SPEC = [
    {
        "fieldname": "custom_legal_entity_section",
        "label": "Receipt Branding (Legal Entity on Printed Receipts)",
        "fieldtype": "Section Break",
        "insert_after": "company",
        "collapsible": 1,
    },
    {
        "fieldname": "custom_legal_entity_name",
        "label": "Legal Entity Name (for receipts)",
        "fieldtype": "Data",
        "insert_after": "custom_legal_entity_section",
        "default": SUNGAS_DEFAULTS["custom_legal_entity_name"],
        "description": (
            "Printed at the top of receipts. Defaults to 'SUNGAS COMPANY LIMITED'. "
            "Override per outlet (e.g. 'BOBO GAS' on POS - Itele)."
        ),
    },
    {
        "fieldname": "custom_legal_entity_tin",
        "label": "Legal Entity TIN",
        "fieldtype": "Data",
        "insert_after": "custom_legal_entity_name",
        "default": SUNGAS_DEFAULTS["custom_legal_entity_tin"],
        "description": "FIRS Tax Identification Number, printed on every receipt. Mandatory per FIRS.",
    },
    {
        "fieldname": "custom_legal_entity_address",
        "label": "Legal Entity Registered Address",
        "fieldtype": "Small Text",
        "insert_after": "custom_legal_entity_tin",
        "default": SUNGAS_DEFAULTS["custom_legal_entity_address"],
        "description": "Registered office address printed below the entity name on receipts.",
    },
]


def ensure_custom_fields():
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields  # type: ignore
    create_custom_fields({"POS Profile": CUSTOM_FIELDS_SPEC}, ignore_validate=True)
    print(f"  + Ensured {len(CUSTOM_FIELDS_SPEC)} custom fields on POS Profile")


def backfill_sungas_defaults():
    """Set Sungas defaults on every enabled POS Profile that doesn't have
    a value yet (idempotent -- preserves any manual edits)."""
    profiles = frappe.get_all(
        "POS Profile",
        filters={"disabled": 0},
        pluck="name",
        order_by="name",
    )
    print(f"\n  Backfilling Sungas defaults across {len(profiles)} profiles:")
    for pname in profiles:
        cur = frappe.db.get_value(
            "POS Profile", pname,
            list(SUNGAS_DEFAULTS.keys()),
            as_dict=True,
        ) or {}
        changed = []
        for k, v in SUNGAS_DEFAULTS.items():
            if not (cur.get(k) or "").strip():
                frappe.db.set_value("POS Profile", pname, k, v, update_modified=False)
                changed.append(k)
        if changed:
            print(f"    + {pname}: set {changed}")
        else:
            print(f"    = {pname}: already populated, no change")


def apply_overrides():
    print("\n  Applying per-profile overrides:")
    for pname, overrides in PROFILE_OVERRIDES.items():
        if not frappe.db.exists("POS Profile", pname):
            print(f"    ! '{pname}' not found, skipping.")
            continue
        applied = []
        for k, v in overrides.items():
            if v is None:
                continue  # keep current value
            cur = frappe.db.get_value("POS Profile", pname, k)
            if cur != v:
                frappe.db.set_value("POS Profile", pname, k, v, update_modified=True)
                applied.append(f"{k}='{v}'")
        if applied:
            print(f"    + {pname}: {applied}")
        else:
            print(f"    = {pname}: already matches overrides")


def main():
    print("=== Receipt branding setup ===")
    ensure_custom_fields()
    backfill_sungas_defaults()
    apply_overrides()
    frappe.db.commit()
    print("\n+ Done. Check POS Profile UI -- you should see a new")
    print("  'Receipt Branding' section with three fields. POS - Itele")
    print("  will show Bobo Gas; all others show Sungas Company Limited.")
    print()


# _BENCH_EXEC_FIX: bench execute "exec(...)" runs scripts with separate
# globals/locals dicts, so module-level functions can't see other module-level
# helpers. Copying locals -> globals before invoking main() fixes the scope.
globals().update(locals())
main()
