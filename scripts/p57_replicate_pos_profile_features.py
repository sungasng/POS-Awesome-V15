"""p57_replicate_pos_profile_features.py
========================================
Replicate selected POS Awesome feature flags from a "golden" POS Profile to
all other enabled outlets.

Use case: a Sungas accountant turns on a few POS Awesome niceties on one
profile during UAT (e.g. partial payment, hold orders, customer wallet,
invoice rounding tweaks) and wants those same flags rolled out everywhere
without per-profile clicking.

Workflow:
  1. Pick a master profile (default: POS - SCL - Ikeja).
  2. Pick the fields to replicate (FIELDS list below -- audit-friendly list).
  3. Run dry-run mode first to print the diff; then re-run with DRY_RUN=False.

Run:
  bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/p57_replicate.py').read())"
"""
import frappe  # type: ignore # noqa: F401

# === EDIT THESE BEFORE RUNNING ==============================================
MASTER_PROFILE = "POS - Ikeja"
DRY_RUN = True   # set to False to actually apply changes

# Fields safe to replicate (POS Awesome behavioural toggles).
# Add to / remove from this list as needed. Run a dry-run first to inspect.
FIELDS = [
    "posa_allow_partial_payment",
    "posa_allow_hold_orders",
    "posa_allow_user_to_edit_rate",
    "posa_allow_user_to_edit_additional_discount",
    "posa_allow_print_draft_invoices",
    "posa_enable_customer_wallet",
    "posa_enable_loyalty",
    "posa_enable_advance_payment",
    "posa_enable_payment_methods_search",
    "posa_use_percentage_discount",
    "posa_round_off_total",
    "posa_force_reload_items",
    "posa_default_qty",
    "posa_hide_closing_shift",
    "posa_pos_view_mode",
    # Rate-control:
    "allow_rate_change_for_items_below_min_rate",
    # Display tweaks:
    "hide_unavailable_items",
    "validate_stock_on_save",
]
# Fields explicitly DO NOT replicate (per-outlet by definition):
SKIP_FIELDS = {
    "name", "company", "cost_center", "warehouse", "branch", "currency",
    "income_account", "expense_account", "write_off_account",
    "applicable_for_users", "payments", "item_groups", "customer_groups",
    "print_format", "letter_head", "tc_name",
    # Don't touch enabled state or default flag.
    "disabled", "is_default",
}
# =============================================================================


def main():
    if not frappe.db.exists("POS Profile", MASTER_PROFILE):
        print(f"  ! Master profile '{MASTER_PROFILE}' not found.")
        return

    master = frappe.get_doc("POS Profile", MASTER_PROFILE).as_dict()
    other_profiles = frappe.get_all(
        "POS Profile",
        filters={"name": ["!=", MASTER_PROFILE], "disabled": 0},
        pluck="name",
        order_by="name",
    )

    # Filter FIELDS to those that actually exist on the doctype
    meta_fields = {df.fieldname for df in frappe.get_meta("POS Profile").fields}
    fields_to_apply = [f for f in FIELDS if f in meta_fields and f not in SKIP_FIELDS]
    missing = [f for f in FIELDS if f not in meta_fields]
    if missing:
        print(f"  (skipping fields not on this POS Profile doctype: {missing})\n")

    print(f"\n=== Replicating from {MASTER_PROFILE} -> {len(other_profiles)} other outlets ===")
    print(f"DRY_RUN: {DRY_RUN}")
    print(f"Fields: {fields_to_apply}\n")

    print(f"Master values: ")
    for f in fields_to_apply:
        print(f"  {f:50s} = {master.get(f)!r}")
    print()

    changes_per_profile = {}
    for pname in other_profiles:
        cur = frappe.db.get_value(
            "POS Profile", pname, fields_to_apply, as_dict=True
        ) or {}
        diffs = []
        for f in fields_to_apply:
            new = master.get(f)
            old = cur.get(f)
            if new != old:
                diffs.append((f, old, new))
        if diffs:
            changes_per_profile[pname] = diffs

    if not changes_per_profile:
        print("All other profiles already match. Nothing to do.\n")
        return

    for pname, diffs in changes_per_profile.items():
        print(f"  ~ {pname}:")
        for f, old, new in diffs:
            print(f"      {f:50s}  {old!r:25s} -> {new!r}")

    if DRY_RUN:
        print("\n(DRY_RUN=True; nothing applied. Re-run with DRY_RUN=False to commit.)\n")
        return

    for pname, diffs in changes_per_profile.items():
        for f, _old, new in diffs:
            frappe.db.set_value("POS Profile", pname, f, new, update_modified=True)
    frappe.db.commit()
    print(f"\n+ Applied changes to {len(changes_per_profile)} profiles.\n")


main()
