"""
THE FIX (after 6 hours of diagnostics):

Frappe v15's get_rendered_template uses this dispatch:

    if print_format.custom_format:        <-- THIS MUST BE 1
        template = get_template_from_string()   # use our html field
    elif print_format.format_data:
        template = "standard"                   # fallback to make_layout
    elif print_format.standard == "Yes":
        template = get_template_from_string()
    else:
        template = "standard"                   # <-- WE WERE HERE

The `custom_format` field is a Check (boolean) on Print Format. When 1,
Frappe uses the html field verbatim. When 0 (default), Frappe ignores
our html and renders via make_layout from the doctype meta -- which is
exactly the "Sr / Row ID / Stock UOM / Distributed Discount" verbose
output the user has been seeing.

This script:
1. Sets custom_format = 1
2. Restores the full Sungas Thermal 58mm html (overwriting the
   ZEBRA_MARKER test template the diagnostics had left in place)
3. Re-renders to confirm SUNGAS COMPANY LIMITED appears

Run on bench:
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/feat/sungas-customizations/scripts/THE_FIX_custom_format.py" \\
      -o /tmp/THE_FIX_custom_format.py && \\
    bench --site sungasmis.v.frappe.cloud execute \\
      "exec(open('/tmp/THE_FIX_custom_format.py').read())"
"""

from __future__ import annotations

import frappe


PRINT_FORMAT_NAME = "Sungas Thermal 58mm"
PROMO_LINE = "GAS DELIVERY NOW AVAILABLE IN PARTNERSHIP WITH VERVEFLAME -- 09055493507, 09055493508."


CSS = r"""
@import url('https://fonts.googleapis.com/css2?family=Libre+Barcode+128&display=swap');
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
.barcode-line {
    font-family: 'Libre Barcode 128', 'Code 128', monospace;
    font-size: 34px !important;
    line-height: 1 !important;
    letter-spacing: 0;
}
.terms { font-size: 9px !important; }
.terms ul { padding-left: 4mm; margin: 1mm 0; }
.terms li { margin: 0; padding: 0; }
.promo { font-size: 9px !important; font-weight: bold; text-align: center; }
.addr { font-size: 9px !important; }
"""

HTML = r"""
{%- set OUTLET_DIRECTORY = {
    "ikeja":           ("9 (old no 1) Obasa Road, Off Oba Akran Avenue, Ikeja, Lagos.", "08077683893, 08108815444, 09055493507, 09055493508"),
    "pedro":           ("38/40 Salami Shuaibu Street, Pedro, Somolu, Lagos.", "08077677436, 09055493507, 09055493508"),
    "bolade":          ("11 Oyetayo Street, Mafoluku, Oshodi, Lagos.", "08077683893, 08108815444, 09055493507, 09055493508"),
    "aseese":          ("Km 32, Lagos-Ibadan Expressway, Aseese Bus-Stop, Ogun State.", "08108815444, 09055493507, 09055493508"),
    "ijuotta":         ("Kilometre 14, Idiroko Road, Iju Town, Custom Bus-Stop, Ogun State.", "08108815444, 09055493507, 09055493508"),
    "osiotta":         ("Ikola Road, 10-10 Bus-Stop, Osi-Ota, Ogun State.", "08108815444, 09055493507, 09055493508"),
    "sefu":            ("Along Sefu Elede Road, Bale Palace Bus-Stop, Ibafo, Ogun State.", "08108815444, 09055493507, 09055493508"),
    "maba":            ("Asese-Maba Town Road off Lagos-Ibadan Expressway, Asese Bus-Stop, Ogun State.", "08108815444, 07059619769, 09055493507, 09055493508"),
    "ijoko":           ("Ijoko-Agbado Road, Abule Bus-Stop, Ijoko-Lemode, Ogun State.", "08077683893, 08108815444, 09055493507, 09055493508"),
    "ebutte":          ("91 Ebute Road, Opp. Gideon Comprehensive High School, Ibafo, Ogun State.", "09049474274, 08108815444, 09055493507, 09055493508"),
    "uppermission":    ("159 Upper Mission Road, Benin City, Edo State.", "08077683770, 09055493507, 09055493508"),
    "idokpa":          ("285 Benin-Auchi Road, Idokpa Qtrs, Benin City, Edo State.", "08108815444, 07059619773, 09055493507, 09055493508"),
    "ekehuan":         ("Opp. Ogede Secondary School, Ekehuan Road, Benin City, Edo State.", "08077683810, 09055493507, 09055493508"),
    "okhuoromi":       ("Along Ebo-Sapele Road, Okhuoromi, Benin City, Edo State.", "08108815444, 09037950596, 09055493507, 09055493508"),
    "idowina":         ("By Underground Church, off Upper Mission Extension, Idowina, Benin City, Edo State.", "08108815444, 07059619773, 09055493507, 09055493508"),
    "asaba":           ("Marine Road, Behind Total Filling Station, Cable Point, Nnebisi Road, Asaba.", "08077683893, 08108815444, 09055493507, 09055493508"),
    "reclamation":     ("7 Reclamation Rd, Macoba, Old Port Harcourt Twp, Port Harcourt.", "09028696786, 09055493507, 09055493508"),
    "eleme":           ("Km 15, PH-Eleme-Bori Road, Eleme, Rivers State.", "08059044977, 09055493507, 09055493508"),
    "itele":           ("52B Adeleye Street, by Shogbade Filling Station, Lafenwa Road, Ayetoro-Itele, Ogun State.", "09022186682, 09055493507, 09055493508"),
    "bulksalesbenin":  ("159 Upper Mission Road, Benin City, Edo State.", "08077683770, 07066691434, 09055493507, 09055493508"),
    "mafoluku":        ("161 Oshodi Road, Mafoluku, Oshodi, Lagos.", "08077683893, 08108815444, 09055493507, 09055493508"),
    "oworo":           ("2 Adeniji Street, Oworonshoki, Kosofe, Lagos.", "08077683893, 08108815444, 09055493507, 09055493508")
} -%}
{%- set company = frappe.get_doc("Company", doc.company) %}
{%- set logo_url = company.company_logo or "/files/sungas-logo.png" %}
{%- set outlet_label_raw = doc.pos_profile.replace("POS - ", "").replace(" (Test)", "") if doc.pos_profile else "" %}
{%- set outlet_key = (outlet_label_raw or "")|lower %}
{%- set outlet_key = outlet_key.replace(" ", "").replace("-", "").replace(".", "") %}
{%- set outlet_info = OUTLET_DIRECTORY.get(outlet_key) %}
{%- set plant_address = outlet_info[0] if outlet_info else "Sungas Company Limited, Nigeria." %}
{%- set contact_phone = outlet_info[1] if outlet_info else "09055493507, 09055493508" %}
{%- set total_qty = (doc.items|sum(attribute="qty"))|round(2) %}
{%- set barcode_payload = doc.name ~ "|" ~ total_qty %}

<div class="print-format">

<div class="center">
    {% if logo_url %}<img class="logo" src="{{ logo_url }}" />{% endif %}
    <div class="brand">{{ (company.company_name or "SUNGAS COMPANY LIMITED")|upper }}</div>
</div>
<div class="dhr"></div>

<table>
    <tr><td>Receipt No:</td><td class="right">{{ doc.name }}</td></tr>
    <tr><td>Cashier:</td><td class="right">{{ doc.owner }}</td></tr>
    <tr><td>Customer:</td><td class="right">{{ doc.customer_name or doc.customer }}</td></tr>
    <tr><td>Date:</td><td class="right">{{ frappe.utils.format_datetime(doc.posting_date, "dd-MM-yyyy") }}</td></tr>
    <tr><td>Time:</td><td class="right">{{ (doc.posting_time|string)[:8] if doc.posting_time else "" }}</td></tr>
    {% if outlet_label_raw %}<tr><td>Outlet:</td><td class="right">{{ outlet_label_raw }}</td></tr>{% endif %}
</table>
<div class="hr"></div>

<table>
    <thead><tr class="bold"><td>Item</td><td class="right" style="width: 11mm;">Qty</td><td class="right" style="width: 19mm;">Amount</td></tr></thead>
    <tbody>
    {% for it in doc.items %}
        <tr>
            <td>{{ it.item_name or it.item_code }}</td>
            <td class="right">{{ "%.2f"|format(it.qty) }}</td>
            <td class="right">{{ frappe.format_value(it.amount, {"fieldtype": "Currency", "options": doc.currency}) }}</td>
        </tr>
        <tr><td colspan="3" class="muted">&nbsp;&nbsp;@ {{ frappe.format_value(it.rate, {"fieldtype": "Currency", "options": doc.currency}) }}{% if it.uom %} / {{ it.uom }}{% endif %}</td></tr>
    {% endfor %}
    </tbody>
</table>
<div class="hr"></div>

<table>
    <tr><td>Subtotal</td><td class="right">{{ frappe.format_value(doc.net_total, {"fieldtype": "Currency", "options": doc.currency}) }}</td></tr>
    {% if doc.total_taxes_and_charges %}<tr><td>Tax</td><td class="right">{{ frappe.format_value(doc.total_taxes_and_charges, {"fieldtype": "Currency", "options": doc.currency}) }}</td></tr>{% endif %}
    {% if doc.discount_amount %}<tr><td>Discount</td><td class="right">- {{ frappe.format_value(doc.discount_amount, {"fieldtype": "Currency", "options": doc.currency}) }}</td></tr>{% endif %}
    <tr><td class="bold">Grand Total</td><td class="right bold">{{ frappe.format_value(doc.grand_total, {"fieldtype": "Currency", "options": doc.currency}) }}</td></tr>
    {% if (doc.rounding_adjustment or 0)|float|abs > 0.01 %}<tr><td>Rounding Adj.</td><td class="right">{{ frappe.format_value(doc.rounding_adjustment, {"fieldtype": "Currency", "options": doc.currency}) }}</td></tr>{% endif %}
    <tr><td class="bold">Rounded Total</td><td class="right bold">{{ frappe.format_value(doc.rounded_total or doc.grand_total, {"fieldtype": "Currency", "options": doc.currency}) }}</td></tr>
</table>
<div class="hr"></div>

<table>
    {% for p in doc.payments %}<tr><td>{{ p.mode_of_payment }}</td><td class="right">{{ frappe.format_value(p.amount, {"fieldtype": "Currency", "options": doc.currency}) }}</td></tr>{% endfor %}
    <tr class="bold"><td>Paid Amount</td><td class="right">{{ frappe.format_value(doc.paid_amount, {"fieldtype": "Currency", "options": doc.currency}) }}</td></tr>
    {% if (doc.change_amount or 0)|float|abs > 0.01 %}<tr><td>Change</td><td class="right">{{ frappe.format_value(doc.change_amount, {"fieldtype": "Currency", "options": doc.currency}) }}</td></tr>{% endif %}
</table>
<div class="hr"></div>

<div class="barcode">
    <div class="barcode-line">*{{ barcode_payload }}*</div>
    <div class="muted">{{ barcode_payload }}</div>
</div>
<div class="hr"></div>

<div class="terms">
    <div class="bold">Terms &amp; Conditions:</div>
    <ul>
        <li>Goods sold are not returnable.</li>
        <li>Check cylinders before leaving the plant.</li>
    </ul>
</div>
<div class="hr"></div>

<div class="addr muted">
    Plant Address: {{ plant_address }}<br/>
    Contact No: {{ contact_phone }}
</div>
<div class="hr"></div>

<div class="promo">__PROMO_LINE__</div>
<div class="hr"></div>

<div class="center bold">Thank you, please visit again.</div>

</div>
""".replace("__PROMO_LINE__", PROMO_LINE)


def main():
    print("=" * 78)
    print(" THE FIX: set custom_format = 1 + restore full Sungas html")
    print("=" * 78)

    pf_meta = frappe.get_meta("Print Format")
    has_custom_format = bool(pf_meta.get_field("custom_format"))
    print(f"\n[0] Print Format has 'custom_format' field: {has_custom_format}")

    frappe.db.sql(
        """UPDATE `tabPrint Format`
           SET custom_format = 1,
               html = %s,
               css  = %s,
               print_format_type = 'Jinja',
               format_data = NULL,
               standard = 'No',
               disabled = 0,
               raw_printing = 0,
               module = NULL
           WHERE name = %s""",
        (HTML, CSS, PRINT_FORMAT_NAME),
    )
    frappe.db.commit()
    frappe.clear_cache()
    try:
        frappe.clear_document_cache("Print Format", PRINT_FORMAT_NAME)
    except Exception:
        pass

    confirm = frappe.db.sql(
        """SELECT custom_format, print_format_type, standard,
                  CHAR_LENGTH(html) AS h, CHAR_LENGTH(css) AS c
           FROM `tabPrint Format` WHERE name=%s""",
        (PRINT_FORMAT_NAME,),
        as_dict=True,
    )[0]
    print(f"\n[1] DB state after fix: {confirm}")

    cand = frappe.db.get_value("POS Invoice", {"docstatus": 1}, "name", order_by="creation desc")
    if cand:
        print(f"\n[2] Server-render test against {cand!r}:")
        rendered = frappe.get_print("POS Invoice", cand, print_format=PRINT_FORMAT_NAME, as_pdf=False)
        ok = "SUNGAS COMPANY LIMITED" in rendered
        bad = "Distributed Discount" in rendered
        print(f"    contains 'SUNGAS COMPANY LIMITED' : {ok}")
        print(f"    contains 'Distributed Discount'   : {bad}")
        if ok and not bad:
            print("\n    *** SUCCESS - Sungas template is rendering ***")
        else:
            print("\n    *** STILL BROKEN - escalate ***")
    print("\n" + "=" * 78)
    print(" Now: bench clear-cache, hard-refresh browser, reprint.")
    print("=" * 78)


try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
