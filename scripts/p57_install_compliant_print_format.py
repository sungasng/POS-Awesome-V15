"""p57_install_compliant_print_format.py
========================================
In-place surgery on 'Sungas Thermal 58mm': add FIRS-compliant elements
WITHOUT disturbing the existing outlet directory, barcode, promo, terms
or visual design that the user already built.

Adds:
  1. RECEIPT label (right under the brand line)
  2. Legal entity name now reads from POS Profile custom_legal_entity_name
     (so Itele prints 'BOBO GAS', everyone else 'SUNGAS COMPANY LIMITED')
  3. TIN line below the brand (reads pos_profile_doc.custom_legal_entity_tin)
  4. Always-show VAT line (currently conditional on total_taxes_and_charges
     being non-zero -- but FIRS expects an explicit VAT @ 0% line for LPG)
  5. Net amount label clarified as 'Subtotal (Net of VAT)'

After running this, the BOBO GAS variant is just a clone (handled by
p57_bobogas_print_format.py separately).

Run:
  bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/p57_compliance.py').read())"

Idempotent: re-runs detect the markers we add and skip if already patched.
"""
import frappe  # type: ignore # noqa: F401

PRINT_FORMAT = "Sungas Thermal 58mm"
PATCH_MARKER = "{# SUNGAS_COMPLIANCE_PATCH_v1 #}"


def patched_html(html: str) -> str:
    if PATCH_MARKER in html:
        return html

    # 1. Inject pos_profile_doc + legal entity vars at the top of the existing
    # set-block (right after the {%- set company = ... line).
    set_block_anchor = '{%- set company = frappe.get_doc("Company", doc.company) %}'
    set_block_replacement = (
        '{%- set company = frappe.get_doc("Company", doc.company) %}\n'
        '{# SUNGAS_COMPLIANCE_PATCH_v1 -- per-outlet legal entity branding #}\n'
        '{%- set pos_profile_doc = frappe.get_doc("POS Profile", doc.pos_profile) if doc.pos_profile else None %}\n'
        '{%- set legal_entity_name = (pos_profile_doc.custom_legal_entity_name if pos_profile_doc else None) or company.company_name or "SUNGAS COMPANY LIMITED" %}\n'
        '{%- set legal_entity_tin = (pos_profile_doc.custom_legal_entity_tin if pos_profile_doc else None) or company.tax_id or "" %}\n'
        '{%- set legal_entity_address = (pos_profile_doc.custom_legal_entity_address if pos_profile_doc else None) or "1, Obasa Road, Ikeja, Lagos" %}\n'
    )
    if set_block_anchor not in html:
        raise Exception(f"Anchor not found: {set_block_anchor[:60]}...")
    html = html.replace(set_block_anchor, set_block_replacement, 1)

    # 2. Replace the brand line: now reads from legal_entity_name + adds RECEIPT
    #    label + TIN line below brand.
    brand_anchor = '<div class="brand">{{ (company.company_name or "SUNGAS COMPANY LIMITED")|upper }}</div>'
    brand_replacement = (
        '<div class="brand">{{ (legal_entity_name or "SUNGAS COMPANY LIMITED")|upper }}</div>\n'
        '    <div class="bold" style="font-size: 11px !important; margin-top: 0.5mm;">RECEIPT</div>\n'
        '    {% if legal_entity_tin %}<div class="muted" style="font-size: 9px !important;">TIN: {{ legal_entity_tin }}</div>{% endif %}\n'
        '    {% if legal_entity_address %}<div class="muted" style="font-size: 9px !important;">{{ legal_entity_address }}</div>{% endif %}'
    )
    if brand_anchor not in html:
        raise Exception(f"Brand anchor not found")
    html = html.replace(brand_anchor, brand_replacement, 1)

    # 3. Replace the conditional Tax row with an always-show VAT row.
    tax_anchor = '{% if doc.total_taxes_and_charges %}<tr><td>Tax</td><td class="right">{{ frappe.format_value(doc.total_taxes_and_charges, {"fieldtype": "Currency", "options": doc.currency}) }}</td></tr>{% endif %}'
    tax_replacement = (
        '<tr><td>VAT @ 0% (LPG - FG waiver)</td>'
        '<td class="right">{{ frappe.format_value(doc.total_taxes_and_charges or 0, {"fieldtype": "Currency", "options": doc.currency}) }}</td></tr>'
    )
    if tax_anchor not in html:
        # try a more flexible match (whitespace tolerant)
        import re
        pattern = re.compile(
            r'\{% if doc\.total_taxes_and_charges %\}<tr><td>Tax</td><td class="right">\{\{ frappe\.format_value\(doc\.total_taxes_and_charges, \{"fieldtype": "Currency", "options": doc\.currency\}\) \}\}</td></tr>\{% endif %\}'
        )
        if pattern.search(html):
            html = pattern.sub(tax_replacement, html, count=1)
        else:
            print("  ! Tax row anchor not found exactly; skipping VAT row replacement.")
            print("    The format may have been edited in UI. Manual edit needed.")
    else:
        html = html.replace(tax_anchor, tax_replacement, 1)

    # 4. Subtotal label clarification (small UX improvement, FIRS expects "Net"
    #    terminology).
    subtotal_anchor = '<tr><td>Subtotal</td><td class="right">{{ frappe.format_value(doc.net_total'
    subtotal_replacement = '<tr><td>Subtotal (Net of VAT)</td><td class="right">{{ frappe.format_value(doc.net_total'
    if subtotal_anchor in html:
        html = html.replace(subtotal_anchor, subtotal_replacement, 1)

    return html


def main():
    if not frappe.db.exists("Print Format", PRINT_FORMAT):
        print(f"  ! Print Format '{PRINT_FORMAT}' not found.")
        return

    pf = frappe.get_doc("Print Format", PRINT_FORMAT)
    if PATCH_MARKER in (pf.html or ""):
        print(f"  = '{PRINT_FORMAT}' already patched (marker found). No change.")
        return

    original_len = len(pf.html or "")
    try:
        new_html = patched_html(pf.html or "")
    except Exception as e:
        print(f"  ! Patch failed: {e}")
        return

    pf.html = new_html
    pf.save(ignore_permissions=True)
    frappe.db.commit()
    print(f"  + Patched '{PRINT_FORMAT}': {original_len} bytes -> {len(new_html)} bytes")
    print(f"  + Marker installed: '{PATCH_MARKER}'")
    print("\n+ Next test print should show:")
    print("    - 'RECEIPT' label under the brand")
    print("    - 'TIN: 00201561-0001' (or BOBO GAS TIN at Itele)")
    print("    - Always-visible 'VAT @ 0% (LPG - FG waiver): 0.00' line")
    print("    - 'Subtotal (Net of VAT)' instead of just 'Subtotal'")


# _BENCH_EXEC_FIX
globals().update(locals())
main()
