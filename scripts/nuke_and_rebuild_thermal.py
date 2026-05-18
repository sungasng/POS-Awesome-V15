"""
Nuclear option: delete the buggy Sungas Thermal 58mm Print Format
entirely and recreate it from scratch with a minimal, syntactically-
clean Jinja template that does NOT use:
  * any Python string-interpolation trick that injects a giant dict literal
  * a module attribution (which can be overridden by on-disk fixtures)
  * any Print Designer / format_data field

If our html still doesn't render after this, the issue isn't the
record -- it's the renderer.

Run on bench:
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/feat/sungas-customizations/scripts/nuke_and_rebuild_thermal.py" \\
      -o /tmp/nuke_and_rebuild_thermal.py && \\
    bench --site sungasmis.v.frappe.cloud execute \\
      "exec(open('/tmp/nuke_and_rebuild_thermal.py').read())"
"""

from __future__ import annotations

import frappe


PRINT_FORMAT_NAME = "Sungas Thermal 58mm"
POS_INVOICE = "POS Invoice"
PROMO_LINE = "GAS DELIVERY NOW AVAILABLE IN PARTNERSHIP WITH VERVEFLAME -- 09055493507, 09055493508."


# Outlet directory baked into the Jinja template as native Jinja syntax
# (no Python string-replace). Jinja can evaluate this dict literal at
# render time -- the previous version's `__OUTLET_DIRECTORY__` placeholder
# trick was a likely source of silent rendering failure.
OUTLET_DIRECTORY_JINJA = """
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
"""


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


# Plain Jinja, no Python string-replace.
HTML = (
    OUTLET_DIRECTORY_JINJA
    + """
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
    {% if frappe.utils.get_barcode_svg is defined %}{{ frappe.utils.get_barcode_svg(barcode_payload) }}{% endif %}
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
""".replace("__PROMO_LINE__", PROMO_LINE)
)


def main():
    print("=" * 78)
    print(f" NUKE + REBUILD: {PRINT_FORMAT_NAME!r}")
    print("=" * 78)

    # ----- Step 1: delete any existing record -----
    if frappe.db.exists("Print Format", PRINT_FORMAT_NAME):
        # delete_doc handles related Property Setters but we want a clean wipe.
        frappe.db.sql(
            "DELETE FROM `tabPrint Format` WHERE name = %s",
            (PRINT_FORMAT_NAME,),
        )
        frappe.db.commit()
        print(f"  [1] deleted existing record")
    else:
        print(f"  [1] no existing record (fresh insert)")

    # ----- Step 2: insert fresh -----
    new = frappe.get_doc({
        "doctype": "Print Format",
        "name": PRINT_FORMAT_NAME,
        "doc_type": POS_INVOICE,
        "module": None,                # no module = no fixture override
        "print_format_type": "Jinja",
        "standard": "No",
        "disabled": 0,
        "font_size": 8,
        "line_breaks": 0,
        "absolute_value": 0,
        "raw_printing": 0,
        "format_data": None,
        "html": HTML,
        "css": CSS,
    })
    new.insert(ignore_permissions=True)
    frappe.db.commit()
    print(f"  [2] inserted fresh record  (html size = {len(HTML)}, css size = {len(CSS)})")

    # ----- Step 3: ensure Property Setter still points here -----
    name = "POS Invoice-main-default_print_format"
    if frappe.db.exists("Property Setter", name):
        frappe.db.set_value("Property Setter", name, "value", PRINT_FORMAT_NAME)
    else:
        frappe.get_doc({
            "doctype": "Property Setter",
            "doctype_or_field": "DocType",
            "doc_type": POS_INVOICE,
            "property": "default_print_format",
            "property_type": "Data",
            "value": PRINT_FORMAT_NAME,
        }).insert(ignore_permissions=True)
    print(f"  [3] Property Setter wired -> {PRINT_FORMAT_NAME!r}")

    # ----- Step 4: re-wire POS Profiles -----
    pp_meta = frappe.get_meta("POS Profile")
    profiles = frappe.get_all("POS Profile", filters={"disabled": 0}, fields=["name"])
    for p in profiles:
        frappe.db.set_value("POS Profile", p.name, "print_format", PRINT_FORMAT_NAME)
        if pp_meta.get_field("print_format_for_online"):
            frappe.db.set_value("POS Profile", p.name, "print_format_for_online", PRINT_FORMAT_NAME)
    print(f"  [4] {len(profiles)} POS Profiles rewired")

    # ----- Step 5: aggressive cache flush -----
    frappe.clear_cache()
    try:
        frappe.clear_document_cache("Print Format", PRINT_FORMAT_NAME)
    except Exception:
        pass
    try:
        frappe.cache().delete_keys("print_format")
    except Exception:
        pass
    frappe.db.commit()
    print(f"  [5] caches flushed")

    # ----- Step 6: server-render to confirm -----
    print(f"\n  [6] Server-render test:")
    cand = frappe.db.get_value("POS Invoice", {"docstatus": 1}, "name", order_by="creation desc")
    if cand:
        rendered = frappe.get_print("POS Invoice", cand, print_format=PRINT_FORMAT_NAME, as_pdf=False)
        ok = "SUNGAS COMPANY LIMITED" in rendered
        bad = "Distributed Discount" in rendered
        print(f"      rendered against {cand!r}")
        print(f"      contains 'SUNGAS COMPANY LIMITED' : {ok}")
        print(f"      contains 'Distributed Discount'   : {bad}")
        if ok and not bad:
            print("      ✓ RECEIPT IS NOW USING OUR JINJA TEMPLATE")
        else:
            print("      ✗ STILL RENDERING STANDARD - escalate")

    print("\n" + "=" * 78)
    print(" Run from shell now:")
    print("    bench --site sungasmis.v.frappe.cloud clear-cache")
    print("    bench --site sungasmis.v.frappe.cloud clear-website-cache")
    print(" Then hard-refresh the browser and re-print any POS Invoice.")
    print("=" * 78)


try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
