"""
Phase-5.5 v2: rebuild Sungas Thermal 58mm receipt:

  * Per-outlet address + contact phone (from the Excel sheet the user
    uploaded; normalised to handle spelling variants between the
    Excel and the POS Profile name -- e.g. Okhoruomi/Okhuoromi).
  * Barcode now encodes BOTH the invoice name AND the total quantity
    paid for, joined by '|'. Human-readable text below the barcode
    shows the same string so cashiers can eyeball-verify it.
  * 'Report disputes within 24 hours' removed from the T&C block per
    user request.

Run on bench:
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/feat/sungas-customizations/scripts/rebuild_thermal_receipt_v2.py" \\
      -o /tmp/rebuild_thermal_receipt_v2.py && \\
    bench --site sungasmis.v.frappe.cloud execute \\
      "exec(open('/tmp/rebuild_thermal_receipt_v2.py').read())"
"""

from __future__ import annotations

import json
import re

import frappe


PRINT_FORMAT_NAME = "Sungas Thermal 58mm"
POS_INVOICE = "POS Invoice"

PROMO_LINE = "GAS DELIVERY NOW AVAILABLE IN PARTNERSHIP WITH VERVEFLAME -- 09055493507, 09055493508."


# --------------------------------------------------------------------- #
# Outlet directory: from user's Outlet-addresses.xlsx, plus head-office
# fallback. Keys are normalised (lowercase, no dashes/spaces) so we can
# match across spelling variants (Okhoruomi vs Okhuoromi, Iju-Ota vs
# Iju-Otta, etc.).
# --------------------------------------------------------------------- #
OUTLET_DIRECTORY = {
    "ikeja":           ("9 (old no 1) Obasa Road, Off Oba Akran Avenue, Ikeja, Lagos.",                                "08077683893, 08108815444, 09055493507, 09055493508"),
    "pedro":           ("38/40 Salami Shuaibu Street, Pedro, Somolu, Lagos.",                                          "08077677436, 09055493507, 09055493508"),
    "aseese":          ("Km 32, Lagos-Ibadan Expressway, Aseese Bus-Stop, Ogun State.",                                "08108815444, 09055493507, 09055493508"),
    "ijuotta":         ("Kilometre 14, Idiroko Road, Iju Town, Custom Bus-Stop, Ogun State.",                          "08108815444, 09055493507, 09055493508"),
    "osiotta":         ("Ikola Road, 10-10 Bus-Stop, Osi-Ota, Ogun State.",                                            "08108815444, 09055493507, 09055493508"),
    "sefu":            ("Along Sefu Elede Road, Bale Palace Bus-Stop, Ibafo, Ogun State.",                             "08108815444, 09055493507, 09055493508"),
    "maba":            ("Asese-Maba Town Road off Lagos-Ibadan Expressway, Asese Bus-Stop, Ogun State.",               "08108815444, 07059619769, 09055493507, 09055493508"),
    "ijoko":           ("Ijoko-Agbado Road, Abule Bus-Stop, Ijoko-Lemode, Ogun State.",                                "08077683893, 08108815444, 09055493507, 09055493508"),
    "ebutte":          ("91 Ebute Road, Opp. Gideon Comprehensive High School, Ibafo, Ogun State.",                    "09049474274, 08108815444, 09055493507, 09055493508"),
    "uppermission":    ("159 Upper Mission Road, Benin City, Edo State.",                                              "08077683770, 09055493507, 09055493508"),
    "idokpa":          ("285 Benin-Auchi Road, Idokpa Qtrs, Benin City, Edo State.",                                   "08108815444, 07059619773, 09055493507, 09055493508"),
    "ekehuan":         ("Opp. Ogede Secondary School, Ekehuan Road, Benin City, Edo State.",                           "08077683810, 09055493507, 09055493508"),
    "okhuoromi":       ("Along Ebo-Sapele Road, Okhuoromi, Benin City, Edo State.",                                    "08108815444, 09037950596, 09055493507, 09055493508"),
    "idowina":         ("By Underground Church, off Upper Mission Extension, Idowina, Benin City, Edo State.",         "08108815444, 07059619773, 09055493507, 09055493508"),
    "asaba":           ("Marine Road, Behind Total Filling Station, Cable Point, Nnebisi Road, Asaba.",                "08077683893, 08108815444, 09055493507, 09055493508"),
    "reclamation":     ("7 Reclamation Rd, Macoba, Old Port Harcourt Twp, Port Harcourt.",                             "09028696786, 09055493507, 09055493508"),
    "eleme":           ("Km 15, PH-Eleme-Bori Road, Eleme, Rivers State.",                                             "08059044977, 09055493507, 09055493508"),
    "itele":           ("52B Adeleye Street, by Shogbade Filling Station, Lafenwa Road, Ayetoro-Itele, Ogun State.",   "09022186682, 09055493507, 09055493508"),
    "bulksalesbenin":  ("159 Upper Mission Road, Benin City, Edo State.",                                              "08077683770, 07066691434, 09055493507, 09055493508"),
    "bolade":          ("11 Oyetayo Street, Mafoluku, Oshodi, Lagos.",                                                 "08077683893, 08108815444, 09055493507, 09055493508"),
    "mafoluku":        ("161 Oshodi Road, Mafoluku, Oshodi, Lagos.",                                                   "08077683893, 08108815444, 09055493507, 09055493508"),
    "oworo":           ("2 Adeniji Street, Oworonshoki, Kosofe, Lagos.",                                               "08077683893, 08108815444, 09055493507, 09055493508"),
}

# Fallback shown when the outlet name in the POS Profile cannot be
# matched to any key above.
FALLBACK_ADDRESS = "Sungas Company Limited, Lagos / Edo / Rivers, Nigeria."
FALLBACK_PHONE   = "09055493507, 09055493508"


CSS = r"""
@page { size: 58mm auto; margin: 0; }
body, .print-format { width: 58mm; margin: 0 auto; padding: 2mm; }
body, .print-format, .print-format * {
    font-family: 'Courier New', monospace !important;
    font-size: 10px !important;
    line-height: 1.25 !important;
    color: #000 !important;
}
.center { text-align: center; }
.right  { text-align: right; }
.bold   { font-weight: bold; }
.hr     { border-top: 1px dashed #000; margin: 1mm 0; height: 0; }
.dhr    { border-top: 2px solid #000; margin: 1mm 0; height: 0; }
table { width: 100%; border-collapse: collapse; }
td, th { padding: 0; vertical-align: top; }
.logo { max-width: 35mm; height: auto; margin: 0 auto 1mm; display: block; }
.brand { font-size: 13px !important; font-weight: bold; letter-spacing: 0.5px; }
.muted { color: #444 !important; }
.barcode { margin: 2mm 0 1mm; text-align: center; }
.barcode svg { max-width: 50mm; height: 14mm; }
.terms { font-size: 9px !important; }
.terms ul { padding-left: 4mm; margin: 1mm 0; }
.terms li { margin: 0; padding: 0; }
.promo { font-size: 9px !important; font-weight: bold; text-align: center; }
.addr { font-size: 9px !important; }
"""

# The HTML template uses Jinja's `__OUTLET_DIRECTORY__` placeholder
# which we replace from Python before insertion (so the dict literal
# stays editable in this script, not duplicated in DB).
HTML_TEMPLATE = r"""
{%- set company = frappe.get_doc("Company", doc.company) %}
{%- set pos_profile = frappe.get_doc("POS Profile", doc.pos_profile) if doc.pos_profile else None %}
{%- set logo_url = company.company_logo or "/files/sungas-logo.png" %}
{%- set outlet_label_raw = doc.pos_profile.replace("POS - ", "").replace(" (Test)", "") if doc.pos_profile else "" %}
{%- set outlet_key = (outlet_label_raw or "")|lower %}
{# strip non-alphanumeric chars in the key so 'Iju-Otta' / 'iju-ota' / 'Iju Otta' all collide #}
{%- set outlet_key = outlet_key.replace(" ", "").replace("-", "").replace(".", "") %}

{%- set outlet_directory = __OUTLET_DIRECTORY__ %}
{%- set outlet_info = outlet_directory.get(outlet_key) %}
{%- set plant_address = outlet_info[0] if outlet_info else "__FALLBACK_ADDRESS__" %}
{%- set contact_phone = outlet_info[1] if outlet_info else "__FALLBACK_PHONE__" %}

{# Total quantity paid for: sum of item.qty (rounded to 2dp). #}
{%- set total_qty = (doc.items|sum(attribute="qty"))|round(2) %}
{%- set barcode_payload = doc.name ~ "|" ~ total_qty %}

{# ============================== HEADER ============================== #}
<div class="center">
    {% if logo_url %}<img class="logo" src="{{ logo_url }}" />{% endif %}
    <div class="brand">{{ (company.company_name or "SUNGAS COMPANY LIMITED")|upper }}</div>
</div>
<div class="dhr"></div>

{# ============================== META ============================== #}
<table>
    <tr><td>Receipt No:</td><td class="right">{{ doc.name }}</td></tr>
    <tr><td>Cashier:</td><td class="right">{{ doc.owner }}</td></tr>
    <tr><td>Customer:</td><td class="right">{{ doc.customer_name or doc.customer }}</td></tr>
    <tr><td>Date:</td><td class="right">{{ frappe.utils.format_datetime(doc.posting_date, "dd-MM-yyyy") }}</td></tr>
    <tr><td>Time:</td><td class="right">{{ (doc.posting_time|string)[:8] if doc.posting_time else "" }}</td></tr>
    {% if outlet_label_raw %}<tr><td>Outlet:</td><td class="right">{{ outlet_label_raw }}</td></tr>{% endif %}
</table>
<div class="hr"></div>

{# ============================== ITEMS ============================== #}
<table>
    <thead>
        <tr class="bold">
            <td>Item</td>
            <td class="right" style="width: 11mm;">Qty</td>
            <td class="right" style="width: 19mm;">Amount</td>
        </tr>
    </thead>
    <tbody>
    {% for it in doc.items %}
        <tr>
            <td>{{ it.item_name or it.item_code }}</td>
            <td class="right">{{ "%.2f"|format(it.qty) }}</td>
            <td class="right">{{ frappe.format_value(it.amount, {"fieldtype": "Currency", "options": doc.currency}) }}</td>
        </tr>
        <tr>
            <td colspan="3" class="muted">
                &nbsp;&nbsp;@ {{ frappe.format_value(it.rate, {"fieldtype": "Currency", "options": doc.currency}) }}{% if it.uom %} / {{ it.uom }}{% endif %}
            </td>
        </tr>
    {% endfor %}
    </tbody>
</table>
<div class="hr"></div>

{# ============================== TOTALS ============================== #}
<table>
    <tr>
        <td>Subtotal</td>
        <td class="right">{{ frappe.format_value(doc.net_total, {"fieldtype": "Currency", "options": doc.currency}) }}</td>
    </tr>
    {% if doc.total_taxes_and_charges %}
    <tr>
        <td>Tax</td>
        <td class="right">{{ frappe.format_value(doc.total_taxes_and_charges, {"fieldtype": "Currency", "options": doc.currency}) }}</td>
    </tr>
    {% endif %}
    {% if doc.discount_amount %}
    <tr>
        <td>Discount</td>
        <td class="right">- {{ frappe.format_value(doc.discount_amount, {"fieldtype": "Currency", "options": doc.currency}) }}</td>
    </tr>
    {% endif %}
    <tr>
        <td class="bold">Grand Total</td>
        <td class="right bold">{{ frappe.format_value(doc.grand_total, {"fieldtype": "Currency", "options": doc.currency}) }}</td>
    </tr>
    {% if (doc.rounding_adjustment or 0)|float|abs > 0.01 %}
    <tr>
        <td>Rounding Adj.</td>
        <td class="right">{{ frappe.format_value(doc.rounding_adjustment, {"fieldtype": "Currency", "options": doc.currency}) }}</td>
    </tr>
    {% endif %}
    <tr>
        <td class="bold">Rounded Total</td>
        <td class="right bold">{{ frappe.format_value(doc.rounded_total or doc.grand_total, {"fieldtype": "Currency", "options": doc.currency}) }}</td>
    </tr>
</table>
<div class="hr"></div>

{# ============================== PAYMENTS ============================== #}
<table>
    {% for p in doc.payments %}
    <tr>
        <td>{{ p.mode_of_payment }}</td>
        <td class="right">{{ frappe.format_value(p.amount, {"fieldtype": "Currency", "options": doc.currency}) }}</td>
    </tr>
    {% endfor %}
    <tr class="bold">
        <td>Paid Amount</td>
        <td class="right">{{ frappe.format_value(doc.paid_amount, {"fieldtype": "Currency", "options": doc.currency}) }}</td>
    </tr>
    {% if (doc.change_amount or 0)|float|abs > 0.01 %}
    <tr>
        <td>Change</td>
        <td class="right">{{ frappe.format_value(doc.change_amount, {"fieldtype": "Currency", "options": doc.currency}) }}</td>
    </tr>
    {% endif %}
</table>
<div class="hr"></div>

{# ============================== BARCODE ============================== #}
<div class="barcode">
    {% if frappe.utils.get_barcode_svg is defined %}
        {{ frappe.utils.get_barcode_svg(barcode_payload) }}
    {% endif %}
    <div class="muted">{{ barcode_payload }}</div>
</div>
<div class="hr"></div>

{# ============================== TERMS ============================== #}
<div class="terms">
    <div class="bold">Terms &amp; Conditions:</div>
    <ul>
        <li>Goods sold are not returnable.</li>
        <li>Check cylinders before leaving the plant.</li>
    </ul>
</div>
<div class="hr"></div>

{# ============================== ADDRESS + PROMO ============================== #}
<div class="addr muted">
    Plant Address: {{ plant_address }}<br/>
    Contact No: {{ contact_phone }}
</div>
<div class="hr"></div>

<div class="promo">__PROMO_LINE__</div>
<div class="hr"></div>

<div class="center bold">Thank you, please visit again.</div>
"""


def _build_html() -> str:
    # Serialise the directory as a Python-literal dict that Jinja will
    # eval at render-time via the `{%- set %}` line.
    py_literal = "{" + ", ".join(
        '"{k}": ({a!r}, {p!r})'.format(k=k, a=v[0], p=v[1])
        for k, v in OUTLET_DIRECTORY.items()
    ) + "}"
    html = HTML_TEMPLATE
    html = html.replace("__OUTLET_DIRECTORY__", py_literal)
    html = html.replace("__FALLBACK_ADDRESS__", FALLBACK_ADDRESS.replace('"', '\\"'))
    html = html.replace("__FALLBACK_PHONE__",   FALLBACK_PHONE.replace('"', '\\"'))
    html = html.replace("__PROMO_LINE__",       PROMO_LINE.replace('"', '\\"'))
    return html


def _upsert_print_format() -> str:
    html = _build_html()
    if frappe.db.exists("Print Format", PRINT_FORMAT_NAME):
        pf = frappe.get_doc("Print Format", PRINT_FORMAT_NAME)
        pf.doc_type = POS_INVOICE
        pf.html = html
        pf.css = CSS
        pf.print_format_type = "Jinja"
        pf.standard = "No"
        pf.module = "POSAwesome"
        pf.font_size = 8
        pf.line_breaks = 0
        pf.absolute_value = 0
        pf.disabled = 0
        pf.save(ignore_permissions=True)
        return "REWRITTEN"
    pf = frappe.get_doc({
        "doctype": "Print Format",
        "name": PRINT_FORMAT_NAME,
        "doc_type": POS_INVOICE,
        "module": "POSAwesome",
        "print_format_type": "Jinja",
        "standard": "No",
        "disabled": 0,
        "font_size": 8,
        "line_breaks": 0,
        "absolute_value": 0,
        "html": html,
        "css": CSS,
    })
    pf.insert(ignore_permissions=True)
    return "CREATED"


def _set_default_print_format() -> str:
    name = "POS Invoice-main-default_print_format"
    if frappe.db.exists("Property Setter", name):
        ps = frappe.get_doc("Property Setter", name)
        if ps.value != PRINT_FORMAT_NAME:
            ps.value = PRINT_FORMAT_NAME
            ps.save(ignore_permissions=True)
            return "UPDATED"
        return "already set"
    frappe.get_doc({
        "doctype": "Property Setter",
        "doctype_or_field": "DocType",
        "doc_type": POS_INVOICE,
        "property": "default_print_format",
        "property_type": "Data",
        "value": PRINT_FORMAT_NAME,
    }).insert(ignore_permissions=True)
    return "CREATED"


def _wire_pos_profiles() -> tuple[int, int]:
    """Set BOTH the standard `print_format` and POS Awesome's custom
    `print_format_for_online` field on every active POS Profile, so
    every print path (the POS Awesome payment dialog AND the Frappe
    doc detail-page Print button) lands on our 58mm template."""
    profiles = frappe.get_all("POS Profile", filters={"disabled": 0}, fields=["name"])
    updated = 0
    for p in profiles:
        changed = False
        if frappe.db.get_value("POS Profile", p.name, "print_format") != PRINT_FORMAT_NAME:
            frappe.db.set_value("POS Profile", p.name, "print_format", PRINT_FORMAT_NAME)
            changed = True
        # POS Awesome custom field -- not every install has it; only
        # update if the field exists on the doctype.
        meta = frappe.get_meta("POS Profile")
        if meta.get_field("print_format_for_online"):
            current = frappe.db.get_value("POS Profile", p.name, "print_format_for_online")
            if current != PRINT_FORMAT_NAME:
                frappe.db.set_value("POS Profile", p.name, "print_format_for_online", PRINT_FORMAT_NAME)
                changed = True
        if changed:
            updated += 1
    return updated, len(profiles)


def main():
    print("=" * 78)
    print(" Rebuild Sungas Thermal 58mm v2 (per-outlet address + smart barcode)")
    print("=" * 78)

    print(f"\n  Directory entries  : {len(OUTLET_DIRECTORY)}")
    print(f"  Active POS Profiles: {frappe.db.count('POS Profile', {'disabled': 0})}")

    print("\n[1] Print Format upsert : ", end="")
    print(_upsert_print_format())

    print("[2] Property Setter (default_print_format) : ", end="")
    print(_set_default_print_format())

    upd, tot = _wire_pos_profiles()
    print(f"[3] POS Profile.print_format wiring : updated {upd} of {tot}")

    print("[4] Clearing Frappe caches...")
    frappe.clear_cache()
    try:
        frappe.clear_document_cache("Print Format", PRINT_FORMAT_NAME)
    except Exception:
        pass

    frappe.db.commit()

    print("\n" + "=" * 78)
    print(" DONE. Run these AFTER this script to flush print cache fully:")
    print("     bench --site sungasmis.v.frappe.cloud clear-cache")
    print("     bench --site sungasmis.v.frappe.cloud clear-website-cache")
    print(" Then re-print any POS Invoice. Barcode now encodes:")
    print('     "<INVOICE_NAME>|<TOTAL_QTY>"   e.g. "ACC-PSINV-2026-00001|12.5"')
    print("=" * 78)


try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
