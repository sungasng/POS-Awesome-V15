"""p57_set_company_tax_id.py
=============================
Set the Tax ID on the ERPNext Company doctype so it's stored at the
canonical company-level location too (in addition to the per-POS-Profile
override fields). ERPNext's standard print formats read this via
{{ doc.company_tax_id }}.

Run:
  bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/p57_company_tax.py').read())"
"""
import frappe  # type: ignore # noqa: F401

COMPANY = "SUNGAS COMPANY LIMITED"
TAX_ID = "00201561-0001"


def main():
    if not frappe.db.exists("Company", COMPANY):
        print(f"  ! Company '{COMPANY}' not found.")
        return
    cur = frappe.db.get_value("Company", COMPANY, "tax_id")
    if cur == TAX_ID:
        print(f"  = Company '{COMPANY}' already has tax_id='{TAX_ID}', no change.")
        return
    frappe.db.set_value("Company", COMPANY, "tax_id", TAX_ID, update_modified=True)
    frappe.db.commit()
    print(f"  + Company '{COMPANY}' tax_id: '{cur}' -> '{TAX_ID}'")


main()
