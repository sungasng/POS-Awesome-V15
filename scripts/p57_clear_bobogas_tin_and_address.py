"""p57_clear_bobogas_tin_and_address.py
========================================
Clear the TIN and address fields on POS - Itele so the Bobo Gas receipt
prints brand name + RECEIPT label only -- no TIN, no header address.

User feedback 2026-06-05 v2 review: the Bobo Gas variant should stay
minimal in the header. Branch address is still printed at the bottom
of the receipt (from the OUTLET_DIRECTORY in the print format).

Run:
  bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/p57_clear_bobo.py').read())"
"""
import frappe  # type: ignore # noqa: F401

PROFILE = "POS - Itele"
FIELDS = ["custom_legal_entity_tin", "custom_legal_entity_address"]


def main():
    if not frappe.db.exists("POS Profile", PROFILE):
        print(f"  ! '{PROFILE}' not found.")
        return
    cur = frappe.db.get_value("POS Profile", PROFILE, FIELDS, as_dict=True) or {}
    print(f"  Before: {dict(cur)}")
    for f in FIELDS:
        frappe.db.set_value("POS Profile", PROFILE, f, "", update_modified=True)
    frappe.db.commit()
    after = frappe.db.get_value("POS Profile", PROFILE, FIELDS, as_dict=True) or {}
    print(f"  After:  {dict(after)}")
    print(f"\n+ Cleared TIN and address on '{PROFILE}'. Bobo Gas receipt will")
    print(f"  no longer print TIN or HQ address lines in the header.")


# _BENCH_EXEC_FIX
globals().update(locals())
main()
