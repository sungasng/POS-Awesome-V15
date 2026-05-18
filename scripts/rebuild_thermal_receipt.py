"""
Phase-5.5 follow-up: rebuild "Sungas Thermal 58mm" Print Format on the
POS Invoice doctype to match the SAMPLE RECEIPT target exactly:

    Header  : Sungas logo + SUNGAS COMPANY LIMITED (centered)
    Meta    : Receipt No / Cashier / Customer / Date / Time / Outlet
    Items   : Item | Qty | Amount  (with @ rate per UOM below)
    Totals  : Subtotal / Grand Total / Rounding Adj / Rounded Total
    Payment : per-mode lines + Paid Amount + Change
    Barcode : Code128 of the invoice number
    T&C     : 3-line block (goods not returnable, check cylinders, 24h)
    Footer  : Plant Address + Contact + promotional msg + "Thank you"

Also:
  - Aggressively clears Frappe's cache so Property Setter
    (default_print_format) takes effect on next print without bench
    restart.
  - Re-asserts POS Profile.print_format wiring.

Run on bench:
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/feat/sungas-customizations/scripts/rebuild_thermal_receipt.py" \\
      -o /tmp/rebuild_thermal_receipt.py && \\
    bench --site sungasmis.v.frappe.cloud execute \\
      "exec(open('/tmp/rebuild_thermal_receipt.py').read())"
"""

from __future__ import annotations

import frappe


PRINT_FORMAT_NAME = "Sungas Thermal 58mm"
POS_INVOICE = "POS Invoice"

# Sungas head-office details (used in the footer + when the warehouse
# has no Address record attached). User can override these in
# `Company.address` / `Warehouse.address` if they want per-plant text.
DEFAULT_PLANT_ADDRESS = "38/40 Salami Shuaibu Street, Pedro, Somolu, Lagos."
DEFAULT_CONTACT_NO    = "08077677436"
PROMO_LINE            = "GAS DELIVERY NOW AVAILABLE IN PARTNERSHIP WITH VERVEFLAME -- 09055493507, 09055493508."


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
"""

HTML = r"""
{%- set company = frappe.get_doc("Company", doc.company) %}
{%- set pos_profile = frappe.get_doc("POS Profile", doc.pos_profile) if doc.pos_profile else None %}
{%- set warehouse_name = doc.set_warehouse or (pos_profile.warehouse if pos_profile else None) %}
{%- set warehouse = frappe.get_doc("Warehouse", warehouse_name) if warehouse_name else None %}
{%- set address = None %}
{%- if warehouse and getattr(warehouse, "address", None) %}
    {%- set address = frappe.get_doc("Address", warehouse.address) %}
{%- endif %}
{%- set logo_url = company.company_logo or "/files/sungas-logo.png" %}
{%- set outlet_label = doc.pos_profile.replace("POS - ", "").replace(" (Test)", "") if doc.pos_profile else "" %}

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
    {% if outlet_label %}<tr><td>Outlet:</td><td class="right">{{ outlet_label }}</td></tr>{% endif %}
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
        {{ frappe.utils.get_barcode_svg(doc.name) }}
    {% endif %}
    <div class="muted">{{ doc.name }}</div>
</div>
<div class="hr"></div>

{# ============================== TERMS ============================== #}
<div class="terms">
    <div class="bold">Terms &amp; Conditions:</div>
    <ul>
        <li>Goods sold are not returnable.</li>
        <li>Check cylinders before leaving the plant.</li>
        <li>Report disputes within 24 hours.</li>
    </ul>
</div>
<div class="hr"></div>

{# ============================== ADDRESS + FOOTER ============================== #}
<div class="muted">
    {% if address %}
        Plant Address: {{ address.address_line1 or "" }}{% if address.address_line2 %}, {{ address.address_line2 }}{% endif %}{% if address.city %}, {{ address.city }}{% endif %}.
        {% if address.phone %}<br/>Contact No: {{ address.phone }}{% endif %}
    {% else %}
        Plant Address: {{ "{{ default_plant_address }}" }}<br/>
        Contact No: {{ "{{ default_contact_no }}" }}
    {% endif %}
</div>
<div class="hr"></div>

<div class="promo">{{ "{{ promo_line }}" }}</div>
<div class="hr"></div>

<div class="center bold">Thank you, please visit again.</div>
"""


def _interpolate_constants(html: str) -> str:
    """Inline the Python-side constants into the Jinja template so users
    can later edit them centrally in this script instead of in the DB."""
    return (
        html
        .replace("{{ default_plant_address }}", DEFAULT_PLANT_ADDRESS)
        .replace("{{ default_contact_no }}",    DEFAULT_CONTACT_NO)
        .replace("{{ promo_line }}",            PROMO_LINE)
    )


def _upsert_print_format() -> str:
    final_html = _interpolate_constants(HTML)

    if frappe.db.exists("Print Format", PRINT_FORMAT_NAME):
        pf = frappe.get_doc("Print Format", PRINT_FORMAT_NAME)
        was_dt = pf.doc_type
        pf.doc_type = POS_INVOICE
        pf.html = final_html
        pf.css = CSS
        pf.print_format_type = "Jinja"
        pf.standard = "No"
        pf.module = "POSAwesome"
        pf.font_size = 8
        pf.line_breaks = 0
        pf.absolute_value = 0
        pf.disabled = 0
        pf.save(ignore_permissions=True)
        return f"REWRITTEN (was on {was_dt!r}, html refreshed)"

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
        "html": final_html,
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
    profiles = frappe.get_all("POS Profile", filters={"disabled": 0}, fields=["name"])
    updated = 0
    for p in profiles:
        if frappe.db.get_value("POS Profile", p.name, "print_format") != PRINT_FORMAT_NAME:
            frappe.db.set_value("POS Profile", p.name, "print_format", PRINT_FORMAT_NAME)
            updated += 1
    return updated, len(profiles)


def main():
    print("=" * 78)
    print(" Rebuild Sungas Thermal 58mm receipt + clear caches")
    print("=" * 78)

    print("\n[1] Print Format upsert : ", end="")
    print(_upsert_print_format())

    print("[2] Property Setter (POS Invoice.default_print_format) : ", end="")
    print(_set_default_print_format())

    upd, tot = _wire_pos_profiles()
    print(f"[3] POS Profile.print_format wiring : updated {upd} of {tot}")

    print("[4] Clearing caches...")
    frappe.clear_cache()
    try:
        frappe.clear_document_cache("Print Format", PRINT_FORMAT_NAME)
    except Exception:
        pass
    try:
        # Invalidate the website renderer's cached print-format chunks.
        frappe.cache().delete_keys("bootinfo")
    except Exception:
        pass

    frappe.db.commit()

    print("\n" + "=" * 78)
    print(" DONE. Re-print POS Invoice now:")
    print("   - From POS Awesome 'Print' button on a completed sale, OR")
    print("   - From the POS Invoice list, open one and click Print")
    print(" If the receipt still looks 'Standard', also run:")
    print("     bench --site sungasmis.v.frappe.cloud clear-cache")
    print("     bench --site sungasmis.v.frappe.cloud clear-website-cache")
    print("=" * 78)


try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
