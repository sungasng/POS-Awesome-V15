"""
Phase-5.5: install the 58mm thermal Print Format for POS Invoice with:
  - Sungas logo at the top
  - Outlet address (from POS Profile -> warehouse -> address)
  - Receipt metadata
  - Item lines with qty x rate / amount
  - Subtotal / Rounding Adjustment / Rounded Total / Paid / Change
  - Barcode of the invoice number (Code128 SVG via frappe.get_barcode_svg)
  - Terms & conditions block (placeholder; user can edit later)

Run on bench:
    curl -fsSL https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/develop/scripts/install_pos_print_format.py \
      -o /tmp/install_pos_print_format.py && \
    bench --site sungasmis.v.frappe.cloud execute \
      "exec(open('/tmp/install_pos_print_format.py').read())"

Then in every POS Profile, set Print Format = 'Sungas Thermal 58mm'.
"""

from __future__ import annotations

import frappe


PRINT_FORMAT_NAME = "Sungas Thermal 58mm"
DOC_TYPE = "POS Invoice"

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
.brand { font-size: 13px !important; font-weight: bold; }
.muted { color: #444 !important; }
.barcode { margin: 2mm 0 1mm; text-align: center; }
.barcode svg { max-width: 50mm; height: 14mm; }
.terms { font-size: 9px !important; }
.terms li { margin-left: 4mm; padding-left: 0; }
"""

HTML = r"""
{%- set company = frappe.get_doc("Company", doc.company) %}
{%- set pos_profile = frappe.get_doc("POS Profile", doc.pos_profile) if doc.pos_profile else None %}
{%- set warehouse = frappe.get_doc("Warehouse", doc.set_warehouse or (pos_profile.warehouse if pos_profile else None)) if (doc.set_warehouse or (pos_profile and pos_profile.warehouse)) else None %}
{%- set address = frappe.get_doc("Address", warehouse.address) if (warehouse and warehouse.address) else None %}
{%- set logo_url = company.company_logo or "/files/sungas-logo.png" %}

<div class="center">
    {% if logo_url %}<img class="logo" src="{{ logo_url }}" />{% endif %}
    <div class="brand">{{ (company.company_name or "SUNGAS COMPANY LIMITED")|upper }}</div>
    {% if address %}
        <div class="muted">{{ address.address_line1 or "" }}</div>
        {% if address.address_line2 %}<div class="muted">{{ address.address_line2 }}</div>{% endif %}
        <div class="muted">
            {{ [address.city, address.state, address.country]|select|join(", ") }}
        </div>
        {% if address.phone %}<div class="muted">Tel: {{ address.phone }}</div>{% endif %}
    {% else %}
        <div class="muted">Plant: {{ doc.set_warehouse or "" }}</div>
    {% endif %}
</div>
<div class="dhr"></div>

<div class="center bold">SALES RECEIPT</div>
<div class="hr"></div>

<table>
    <tr><td>Receipt#</td><td class="right">{{ doc.name }}</td></tr>
    <tr><td>Date</td><td class="right">{{ frappe.utils.format_datetime(doc.posting_date, "dd-MM-yyyy") }}</td></tr>
    <tr><td>Time</td><td class="right">{{ doc.posting_time[:8] if doc.posting_time else "" }}</td></tr>
    <tr><td>Cashier</td><td class="right">{{ doc.owner }}</td></tr>
    <tr><td>Customer</td><td class="right">{{ doc.customer_name or doc.customer }}</td></tr>
    {% if doc.pos_profile %}
    <tr><td>Outlet</td><td class="right">{{ doc.pos_profile.replace("POS - ", "").replace(" (Test)", "") }}</td></tr>
    {% endif %}
</table>
<div class="hr"></div>

<table>
    <thead>
        <tr class="bold">
            <td>Item</td>
            <td class="right" style="width: 12mm;">Qty</td>
            <td class="right" style="width: 18mm;">Amount</td>
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
                &nbsp;&nbsp;@ {{ frappe.format_value(it.rate, {"fieldtype": "Currency", "options": doc.currency}) }} {{ it.uom or "" }}
            </td>
        </tr>
    {% endfor %}
    </tbody>
</table>

<div class="hr"></div>

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
    <tr>
        <td class="bold">Rounded Total</td>
        <td class="right bold">{{ frappe.format_value(doc.rounded_total, {"fieldtype": "Currency", "options": doc.currency}) }}</td>
    </tr>
    {% endif %}
</table>

<div class="hr"></div>

<table>
    {% for p in doc.payments %}
    <tr>
        <td>{{ p.mode_of_payment }}</td>
        <td class="right">{{ frappe.format_value(p.amount, {"fieldtype": "Currency", "options": doc.currency}) }}</td>
    </tr>
    {% endfor %}
    <tr class="bold">
        <td>Paid</td>
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

{# Barcode of the invoice number (Code128). #}
<div class="barcode">
    {{ frappe.utils.get_barcode_svg(doc.name) if frappe.utils.get_barcode_svg is defined else "" }}
    <div class="muted">{{ doc.name }}</div>
</div>

<div class="hr"></div>

<div class="terms">
    <div class="bold">Terms &amp; Conditions:</div>
    <ul>
        <li>Goods sold are not returnable.</li>
        <li>Check cylinders before leaving the plant.</li>
        <li>Report disputes within 24 hours.</li>
    </ul>
    {% if doc.terms %}
    <div>{{ doc.terms|safe }}</div>
    {% endif %}
</div>

<div class="hr"></div>
<div class="center bold">Thank you, please visit again.</div>
{% if pos_profile and pos_profile.company %}
<div class="center muted">{{ pos_profile.company }}</div>
{% endif %}
"""


def main():
    print("Installing Print Format:", PRINT_FORMAT_NAME)
    if frappe.db.exists("Print Format", PRINT_FORMAT_NAME):
        pf = frappe.get_doc("Print Format", PRINT_FORMAT_NAME)
        pf.doc_type = DOC_TYPE
        pf.print_format_type = "Jinja"
        pf.font_size = 8
        pf.line_breaks = 0
        pf.absolute_value = 0
        pf.standard = "No"
        pf.disabled = 0
        pf.html = HTML
        pf.css = CSS
        pf.module = "POSAwesome"
        pf.save(ignore_permissions=True)
        action = "UPDATED"
    else:
        pf = frappe.get_doc({
            "doctype": "Print Format",
            "name": PRINT_FORMAT_NAME,
            "doc_type": DOC_TYPE,
            "module": "POSAwesome",
            "print_format_type": "Jinja",
            "standard": "No",
            "disabled": 0,
            "font_size": 8,
            "line_breaks": 0,
            "absolute_value": 0,
            "html": HTML,
            "css": CSS,
        })
        pf.insert(ignore_permissions=True)
        action = "CREATED"
    frappe.db.commit()
    print(f"  -> {action}: {PRINT_FORMAT_NAME} (doctype={DOC_TYPE})")
    print("\nNext step: in every POS Profile, set Print Format =", PRINT_FORMAT_NAME)
    print("           and upload the logo PNG to File doctype as 'sungas-logo.png'")
    print("           (or set Company.company_logo via /app/company).")


try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
