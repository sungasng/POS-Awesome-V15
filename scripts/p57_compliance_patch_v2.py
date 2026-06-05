"""p57_compliance_patch_v2.py
==============================
Second-pass surgical fixes on 'Sungas Thermal 58mm' after user review of
v1 receipts on 2026-06-05:

  1. Remove the logo image (user wants both Sungas and Bobo Gas receipts
     clean of the SUNGAS logo bitmap).
  2. Stop falling back to "1, Obasa Road, Ikeja, Lagos" when a profile
     leaves the address blank. Bobo Gas (Itele) intentionally has no
     address override, so the v1 patch was bleeding the Sungas HQ address
     onto the Bobo Gas receipt.
  3. Simplify the VAT label from "VAT @ 0% (LPG - FG waiver)" to just
     "VAT @ 0%". Compliance officers only need the rate; the rationale
     belongs in the FIRS schedule, not the customer receipt.

Run:
  bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/p57_v2.py').read())"

Idempotent: marks the HTML with v2 sentinel; safe to re-run.
"""
import frappe  # type: ignore # noqa: F401

PRINT_FORMAT = "Sungas Thermal 58mm"
V2_MARKER = "{# SUNGAS_COMPLIANCE_PATCH_v2 #}"


def patched_v2(html: str) -> str:
    if V2_MARKER in html:
        return html

    # Fix 1: drop the logo img line. The whole <img class="logo" .../> tag
    # is wrapped in {% if logo_url %} ... {% endif %} so we strip both.
    logo_anchor = '    {% if logo_url %}<img class="logo" src="{{ logo_url }}" />{% endif %}\n'
    if logo_anchor in html:
        html = html.replace(logo_anchor, "", 1)
    else:
        # Try without trailing newline
        logo_anchor_2 = '{% if logo_url %}<img class="logo" src="{{ logo_url }}" />{% endif %}'
        if logo_anchor_2 in html:
            html = html.replace(logo_anchor_2, "", 1)
        else:
            print("  ! logo anchor not found (already removed?)")

    # Fix 2: stop falling back to "1, Obasa Road" when profile has no
    # custom_legal_entity_address. Profile-empty => no address line.
    fallback_anchor = (
        '{%- set legal_entity_address = (pos_profile_doc.custom_legal_entity_address if pos_profile_doc else None) '
        'or "1, Obasa Road, Ikeja, Lagos" %}'
    )
    fallback_replacement = (
        '{%- set legal_entity_address = (pos_profile_doc.custom_legal_entity_address if pos_profile_doc else None) or "" %}'
    )
    if fallback_anchor in html:
        html = html.replace(fallback_anchor, fallback_replacement, 1)
    else:
        print("  ! address fallback anchor not found (already removed?)")

    # Fix 3: simplify VAT label.
    vat_old = '<tr><td>VAT @ 0% (LPG - FG waiver)</td>'
    vat_new = '<tr><td>VAT @ 0%</td>'
    if vat_old in html:
        html = html.replace(vat_old, vat_new, 1)
    else:
        # Maybe it has been edited manually since v1 -- look for a flexible match
        import re
        if re.search(r'<tr><td>VAT @ 0%[^<]*</td>', html):
            html = re.sub(r'<tr><td>VAT @ 0%[^<]*</td>', vat_new, html, count=1)
        else:
            print("  ! VAT label anchor not found")

    # Insert the v2 marker right after the v1 marker so future re-runs detect us.
    v1_marker = "{# SUNGAS_COMPLIANCE_PATCH_v1 #}"
    if v1_marker in html:
        html = html.replace(v1_marker, v1_marker + "\n" + V2_MARKER, 1)
    else:
        # Belt-and-braces: append at top if v1 marker missing
        html = V2_MARKER + "\n" + html

    return html


def main():
    if not frappe.db.exists("Print Format", PRINT_FORMAT):
        print(f"  ! Print Format '{PRINT_FORMAT}' not found.")
        return

    pf = frappe.get_doc("Print Format", PRINT_FORMAT)
    if V2_MARKER in (pf.html or ""):
        print(f"  = '{PRINT_FORMAT}' already patched (v2 marker found). No change.")
        return

    before_len = len(pf.html or "")
    pf.html = patched_v2(pf.html or "")
    pf.save(ignore_permissions=True)
    frappe.db.commit()
    print(f"  + Patched '{PRINT_FORMAT}' v2: {before_len} -> {len(pf.html)} bytes")
    print("\nNext test print should show:")
    print("  - NO logo image at the top")
    print("  - For Bobo Gas (Itele): no Sungas HQ address bleeding through")
    print("  - VAT line simplified to 'VAT @ 0%'")


# _BENCH_EXEC_FIX
globals().update(locals())
main()
