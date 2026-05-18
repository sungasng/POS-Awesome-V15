"""
Phase-5.5 follow-up: install the lean Sungas 58mm thermal Print Format
for the Sales Invoice doctype (in addition to POS Invoice), set it as
the default print format for Sales Invoice, and wire every POS Profile
to use it.

Why this is needed
------------------
POS Awesome submits a POS Invoice then ERPNext consolidates it into a
Sales Invoice. When the user clicks "Print" on the resulting Sales
Invoice (e.g. ACC-SINV-2026-00041), Frappe falls back to the built-in
"Standard" Sales Invoice template, which dumps every accounting field
(Cost Center, Distributed Discount Amount, Update Billed, Row ID,
Stock UOM, Eligible for Commission, Sales and Marketing, etc.) onto
the 58mm strip and produces a messy wrap-around receipt.

This script reuses the exact same HTML/CSS already proven on the POS
Invoice format and:
  1. Creates / refreshes "Sungas Thermal 58mm" for doctype = Sales Invoice
  2. Sets Print Settings.with_letterhead = 0 (cleaner thermal output)
  3. Updates every POS Profile.print_format to point at it
  4. Sets the Property Setter so Sales Invoice's default_print_format
     uses the new template (so the standard "Print" button picks it up
     without manual selection)

Run on bench (pin to feat branch HEAD or commit SHA):
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/feat/sungas-customizations/scripts/install_sales_invoice_thermal.py" \\
      -o /tmp/install_sales_invoice_thermal.py && \\
    bench --site sungasmis.v.frappe.cloud execute \\
      "exec(open('/tmp/install_sales_invoice_thermal.py').read())"
"""

from __future__ import annotations

import frappe


PRINT_FORMAT_NAME = "Sungas Thermal 58mm"
SALES_INVOICE = "Sales Invoice"


# Identical to install_pos_print_format.py -- intentional. One source of
# truth for the receipt look-and-feel.
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
{%- set warehouse_name = doc.set_warehouse or (pos_profile.warehouse if pos_profile else None) %}
{%- set warehouse = frappe.get_doc("Warehouse", warehouse_name) if warehouse_name else None %}
{%- set address = frappe.get_doc("Address", warehouse.address) if (warehouse and getattr(warehouse, "address", None)) else None %}
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
    {% elif warehouse_name %}
        <div class="muted">Plant: {{ warehouse_name }}</div>
    {% endif %}
</div>
<div class="dhr"></div>

<div class="center bold">SALES RECEIPT</div>
<div class="hr"></div>

<table>
    <tr><td>Receipt#</td><td class="right">{{ doc.name }}</td></tr>
    <tr><td>Date</td><td class="right">{{ frappe.utils.format_datetime(doc.posting_date, "dd-MM-yyyy") }}</td></tr>
    <tr><td>Time</td><td class="right">{{ (doc.posting_time|string)[:8] if doc.posting_time else "" }}</td></tr>
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
</div>

<div class="hr"></div>
<div class="center bold">Thank you, please visit again.</div>
"""


def _upsert_print_format(doctype: str) -> str:
    """Create or refresh `Sungas Thermal 58mm` for the given doctype.
    The Print Format name is shared across doctypes via the unique
    constraint on (name, doc_type); we use one PF per doctype keyed by
    the same display name to keep the cashier UX consistent."""
    # Frappe lets two Print Format records share the same `name` only if
    # they target different doctypes. We disambiguate by querying with
    # both filters.
    existing = frappe.db.get_value(
        "Print Format",
        {"name": PRINT_FORMAT_NAME, "doc_type": doctype},
        "name",
    )
    if existing:
        pf = frappe.get_doc("Print Format", existing)
        pf.html = HTML
        pf.css = CSS
        pf.font_size = 8
        pf.line_breaks = 0
        pf.absolute_value = 0
        pf.disabled = 0
        pf.print_format_type = "Jinja"
        pf.standard = "No"
        pf.module = "POSAwesome"
        pf.save(ignore_permissions=True)
        return "UPDATED"

    pf = frappe.get_doc({
        "doctype": "Print Format",
        "name": PRINT_FORMAT_NAME,
        "doc_type": doctype,
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
    return "CREATED"


def _set_default_print_format_for_sales_invoice():
    """Use a Property Setter so Sales Invoice's default_print_format
    points at our 58mm receipt. This is what Frappe's standard "Print"
    button reads when no per-doc override is set."""
    name = f"Sales Invoice-main-default_print_format"
    if frappe.db.exists("Property Setter", name):
        ps = frappe.get_doc("Property Setter", name)
        ps.value = PRINT_FORMAT_NAME
        ps.save(ignore_permissions=True)
        return "UPDATED"

    ps = frappe.get_doc({
        "doctype": "Property Setter",
        "doctype_or_field": "DocType",
        "doc_type": SALES_INVOICE,
        "property": "default_print_format",
        "property_type": "Data",
        "value": PRINT_FORMAT_NAME,
    })
    ps.insert(ignore_permissions=True)
    return "CREATED"


def _disable_letterhead_globally():
    """Strip the letterhead from thermal prints. Cashiers don't want a
    A4 logo banner squashed onto 58mm paper."""
    try:
        ps = frappe.get_doc("Print Settings", "Print Settings")
        if ps.with_letterhead:
            ps.with_letterhead = 0
            ps.save(ignore_permissions=True)
            return True
    except Exception as exc:
        print(f"  WARN: could not update Print Settings: {exc}")
    return False


def _wire_pos_profile_print_formats():
    """Set every POS Profile.print_format to our lean template so the
    POS Awesome 'Print' button uses it as well."""
    profiles = frappe.get_all("POS Profile", fields=["name", "disabled"])
    changed = 0
    for p in profiles:
        if p.disabled:
            continue
        doc = frappe.get_doc("POS Profile", p.name)
        if doc.print_format == PRINT_FORMAT_NAME:
            continue
        doc.print_format = PRINT_FORMAT_NAME
        doc.save(ignore_permissions=True)
        changed += 1
    return len(profiles), changed


def main():
    print("=" * 78)
    print(" Install Sungas Thermal 58mm for Sales Invoice + wire defaults")
    print("=" * 78)

    print(f"\n[1] Print Format on POS Invoice : ", end="")
    print(_upsert_print_format("POS Invoice"))

    print(f"[2] Print Format on Sales Invoice: ", end="")
    print(_upsert_print_format("Sales Invoice"))

    print(f"[3] Sales Invoice default_print_format : ", end="")
    print(_set_default_print_format_for_sales_invoice())

    print(f"[4] Print Settings.with_letterhead = 0 : ", end="")
    print("APPLIED" if _disable_letterhead_globally() else "already 0")

    total, changed = _wire_pos_profile_print_formats()
    print(f"[5] POS Profile.print_format updated   : {changed} of {total}")

    frappe.db.commit()
    print("\nDone. Cashiers can now print a clean 58mm receipt from either")
    print("the POS Awesome dialog OR the Sales Invoice 'Print' button.")


try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
