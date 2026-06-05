"""p57_compliance_patch_v3.py
==============================
Third-pass fix on 'Sungas Thermal 58mm' after user review of v2 receipts
on 2026-06-05:

  - User cleared TIN + address on POS - Itele, but Bobo Gas receipt
    STILL showed TIN: 00201561-0001 + 1, Obasa Road, Ikeja, Lagos.
  - Root cause: the v1 Jinja used Python `or` chaining:
      legal_entity_tin = (profile.tin if profile else None)
                         or company.tax_id or ""
    When profile.tin is "" (empty string), Python `or` falls through to
    company.tax_id which is set to '00201561-0001' on SUNGAS COMPANY
    LIMITED. So Bobo Gas (empty field) inherited Sungas TIN. Same bug
    for address.

  - Fix: drop the company-level fallbacks. Since the branding script
    backfilled all 22 profiles with explicit values, only outlets we
    INTENTIONALLY cleared (Bobo Gas / Itele) will show empty.

Run:
  bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/p57_v3.py').read())"

Idempotent via V3_MARKER sentinel.
"""
import frappe  # type: ignore # noqa: F401

PRINT_FORMAT = "Sungas Thermal 58mm"
V3_MARKER = "{# SUNGAS_COMPLIANCE_PATCH_v3 #}"


def patched_v3(html: str) -> str:
    if V3_MARKER in html:
        return html

    # Fix the TIN fallback: drop ` or company.tax_id or ""`
    tin_old = '{%- set legal_entity_tin = (pos_profile_doc.custom_legal_entity_tin if pos_profile_doc else None) or company.tax_id or "" %}'
    tin_new = '{%- set legal_entity_tin = pos_profile_doc.custom_legal_entity_tin if pos_profile_doc else "" %}'
    if tin_old in html:
        html = html.replace(tin_old, tin_new, 1)
    else:
        print("  ! tin set-line anchor not found (already patched or modified?)")

    # Fix the address fallback: drop ` or ""` clause too (v2 already removed
    # the HQ default, but the wrapping `or` still pulls company-level data
    # via earlier patches if anyone re-enables; explicit pos-profile-only
    # assignment is cleanest).
    addr_old = '{%- set legal_entity_address = (pos_profile_doc.custom_legal_entity_address if pos_profile_doc else None) or "" %}'
    addr_new = '{%- set legal_entity_address = pos_profile_doc.custom_legal_entity_address if pos_profile_doc else "" %}'
    if addr_old in html:
        html = html.replace(addr_old, addr_new, 1)
    else:
        print("  ! address set-line anchor not found (already patched or modified?)")

    # Install v3 marker after v2 marker (or v1, whichever is last)
    for marker in ["{# SUNGAS_COMPLIANCE_PATCH_v2 #}", "{# SUNGAS_COMPLIANCE_PATCH_v1 #}"]:
        if marker in html:
            html = html.replace(marker, marker + "\n" + V3_MARKER, 1)
            break
    else:
        html = V3_MARKER + "\n" + html

    return html


def main():
    if not frappe.db.exists("Print Format", PRINT_FORMAT):
        print(f"  ! Print Format '{PRINT_FORMAT}' not found.")
        return
    pf = frappe.get_doc("Print Format", PRINT_FORMAT)
    if V3_MARKER in (pf.html or ""):
        print(f"  = '{PRINT_FORMAT}' already patched (v3 marker found). No change.")
        return
    before = len(pf.html or "")
    pf.html = patched_v3(pf.html or "")
    pf.save(ignore_permissions=True)
    frappe.db.commit()
    print(f"  + Patched '{PRINT_FORMAT}' v3: {before} -> {len(pf.html)} bytes")
    print("\nNext test print should show:")
    print("  - Sungas (Ikeja): TIN: 00201561-0001 + HQ address (unchanged)")
    print("  - Bobo Gas (Itele): brand + RECEIPT only, no TIN, no address")


# _BENCH_EXEC_FIX
globals().update(locals())
main()
