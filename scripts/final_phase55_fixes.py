"""
Final Phase-5.5 fixes:

1. Embed Libre Barcode 128 font as base64 @font-face in the Print Format
   CSS so the barcode actually renders (Frappe Cloud's PDF renderer
   doesn't fetch external CSS resources).
2. Reverse the over-broad Customer-Group user permission so cashiers
   can SELL to any customer group, but force NEW customers they
   create to default to Retail (read-only field, enforced via Client
   Script and best-effort Server Script).
3. Block cashiers from EDITING existing customers (Client Script
   disables save + dimmed banner; Server Script enforces server-side
   if the site allows Server Scripts).

Run:
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/feat/sungas-customizations/scripts/final_phase55_fixes.py" \\
      -o /tmp/final_phase55_fixes.py && \\
    bench --site sungasmis.v.frappe.cloud execute \\
      "exec(open('/tmp/final_phase55_fixes.py').read())"
"""

from __future__ import annotations

import base64

import frappe
import requests


PRINT_FORMAT_NAME = "Sungas Thermal 58mm"
LPG_POS_ROLE = "LPG POS User"
RETAIL_GROUP = "Retail"

# Google Fonts open-source mirror -- this is the actual TTF served when
# you hit the Google Fonts CSS for Libre Barcode 128. Stable since 2018.
LIBRE_BARCODE_TTF_URL = (
    "https://github.com/google/fonts/raw/main/ofl/librebarcode128/LibreBarcode128-Regular.ttf"
)


# --------------------------------------------------------------------- #
# 1) Barcode font embed
# --------------------------------------------------------------------- #
def fetch_font_base64() -> str:
    print(f"  fetching {LIBRE_BARCODE_TTF_URL!r}...")
    r = requests.get(LIBRE_BARCODE_TTF_URL, timeout=30)
    r.raise_for_status()
    b64 = base64.b64encode(r.content).decode("ascii")
    print(f"  font fetched: {len(r.content):,} bytes -> {len(b64):,} base64 chars")
    return b64


def rebuild_css_with_embedded_font(font_b64: str) -> str:
    return (
        "@font-face {\n"
        "    font-family: 'Libre Barcode 128';\n"
        "    font-style: normal;\n"
        "    font-weight: 400;\n"
        f"    src: url(data:font/truetype;charset=utf-8;base64,{font_b64}) format('truetype');\n"
        "}\n"
        + r"""@page { size: 58mm auto; margin: 0; }
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
    font-family: 'Libre Barcode 128' !important;
    font-size: 38px !important;
    line-height: 1 !important;
    letter-spacing: 0 !important;
    color: #000 !important;
}
.terms { font-size: 9px !important; }
.terms ul { padding-left: 4mm; margin: 1mm 0; }
.terms li { margin: 0; padding: 0; }
.promo { font-size: 9px !important; font-weight: bold; text-align: center; }
.addr { font-size: 9px !important; }
"""
    )


def apply_barcode_fix():
    print("\n[1] Embed Libre Barcode 128 font in Print Format CSS")
    try:
        b64 = fetch_font_base64()
    except Exception as exc:
        print(f"  WARN: could not fetch font ({exc}); barcode will fall back to text.")
        return False
    new_css = rebuild_css_with_embedded_font(b64)
    frappe.db.set_value("Print Format", PRINT_FORMAT_NAME, "css", new_css)
    frappe.db.commit()
    print(f"  CSS updated: new size = {len(new_css):,} chars (incl. embedded font)")
    return True


# --------------------------------------------------------------------- #
# 2) Reverse Customer Group user permission
# --------------------------------------------------------------------- #
def reverse_customer_group_user_permission():
    print(f"\n[2] Remove Customer Group = {RETAIL_GROUP!r} user permissions")
    rows = frappe.get_all(
        "User Permission",
        filters={"allow": "Customer Group", "for_value": RETAIL_GROUP},
        fields=["name", "user"],
    )
    if not rows:
        print("  no matching User Permission rows -- nothing to remove")
        return
    for r in rows:
        frappe.db.delete("User Permission", r.name)
    frappe.db.commit()
    print(f"  removed {len(rows)} User Permission row(s) "
          f"(cashiers can now SEE all customer groups in POS search)")


# --------------------------------------------------------------------- #
# 3) Property Setter -- default Customer.customer_group = Retail
# --------------------------------------------------------------------- #
def set_customer_group_default():
    print(f"\n[3] Customer.customer_group default -> {RETAIL_GROUP!r}")
    if not frappe.db.exists("Customer Group", RETAIL_GROUP):
        print(f"  WARN: Customer Group {RETAIL_GROUP!r} not found -- skipping")
        return
    name = "Customer-customer_group-default"
    if frappe.db.exists("Property Setter", name):
        frappe.db.set_value("Property Setter", name, "value", RETAIL_GROUP)
    else:
        frappe.get_doc({
            "doctype": "Property Setter",
            "doctype_or_field": "DocField",
            "doc_type": "Customer",
            "field_name": "customer_group",
            "property": "default",
            "property_type": "Text",
            "value": RETAIL_GROUP,
        }).insert(ignore_permissions=True)
    frappe.db.commit()
    print("  done")


# --------------------------------------------------------------------- #
# 4) Client Script -- restrict cashier UX on Customer form
# --------------------------------------------------------------------- #
CLIENT_SCRIPT = r"""// Cashier-side restrictions on Customer form.
// Goal: cashiers (LPG POS User) can CREATE customers only in
// "Retail" group, and CANNOT edit existing customers at all.
frappe.ui.form.on("Customer", {
    refresh(frm) {
        const roles = frappe.user_roles || [];
        const is_cashier = roles.includes("LPG POS User");
        const is_senior = roles.some(r =>
            ["System Manager", "Sales Manager", "Accounts Manager",
             "LPG Plant Manager", "LPG Head of Sales", "LPG Head of Finance"].includes(r)
        );
        if (!is_cashier || is_senior) {
            return;
        }

        if (frm.is_new()) {
            // Cashier is creating a new customer -- lock group to Retail.
            frm.set_value("customer_group", "Retail");
            frm.set_df_property("customer_group", "read_only", 1);
            frm.set_df_property("customer_group", "description",
                "Cashiers may only create customers in the Retail group.");
        } else {
            // Cashier opened an existing customer -- view only.
            frm.disable_save();
            frm.fields.forEach(f => {
                if (f.df && !["customer_name", "customer_group", "territory",
                              "mobile_no", "email_id"].includes(f.df.fieldname)) {
                    return;
                }
            });
            // Make every field read-only.
            for (const fn of Object.keys(frm.fields_dict || {})) {
                try { frm.set_df_property(fn, "read_only", 1); }
                catch (e) { /* ignore */ }
            }
            frm.dashboard.add_indicator(
                __("View only -- cashiers cannot edit customer profiles"), "orange");
        }
    },
});
"""


def install_client_script():
    print("\n[4] Customer form Client Script -- restrict cashier UX")
    name = "Sungas - Cashier Customer Restrictions"
    payload = {
        "doctype": "Client Script",
        "name": name,
        "dt": "Customer",
        "view": "Form",
        "enabled": 1,
        "script": CLIENT_SCRIPT,
    }
    if frappe.db.exists("Client Script", name):
        doc = frappe.get_doc("Client Script", name)
        doc.script = CLIENT_SCRIPT
        doc.enabled = 1
        doc.view = "Form"
        doc.save(ignore_permissions=True)
        print(f"  updated existing Client Script {name!r}")
    else:
        frappe.get_doc(payload).insert(ignore_permissions=True)
        print(f"  created Client Script {name!r}")
    frappe.db.commit()


# --------------------------------------------------------------------- #
# 5) Server Script (best-effort) -- server-side hardening
# --------------------------------------------------------------------- #
SERVER_SCRIPT_INSERT = r"""
# Server Script: enforce Customer Group = Retail when a cashier
# (LPG POS User without senior roles) creates a customer.
SENIORS = {"System Manager", "Sales Manager", "Accounts Manager",
           "LPG Plant Manager", "LPG Head of Sales", "LPG Head of Finance"}
user_roles = set(frappe.get_roles(frappe.session.user))
if "LPG POS User" in user_roles and not (user_roles & SENIORS):
    doc.customer_group = "Retail"
"""

SERVER_SCRIPT_UPDATE = r"""
# Server Script: block customer edits by cashiers (LPG POS User
# without senior roles). Insertion is allowed; update is not.
if not doc.is_new():
    SENIORS = {"System Manager", "Sales Manager", "Accounts Manager",
               "LPG Plant Manager", "LPG Head of Sales", "LPG Head of Finance"}
    user_roles = set(frappe.get_roles(frappe.session.user))
    if "LPG POS User" in user_roles and not (user_roles & SENIORS):
        frappe.throw("Cashiers cannot edit existing customer profiles.")
"""


def install_server_scripts():
    print("\n[5] Server Scripts (best-effort -- may be disabled on this site)")
    if not frappe.db.exists("DocType", "Server Script"):
        print("  Server Script doctype not present; skipping")
        return
    targets = [
        ("Sungas - Force Retail Group On Customer Insert",
         "before_insert", SERVER_SCRIPT_INSERT),
        ("Sungas - Block Customer Edits By Cashier",
         "before_save", SERVER_SCRIPT_UPDATE),
    ]
    for name, event, body in targets:
        payload = {
            "doctype": "Server Script",
            "name": name,
            "script_type": "DocType Event",
            "reference_doctype": "Customer",
            "doctype_event": event,
            "disabled": 0,
            "script": body.strip(),
        }
        try:
            if frappe.db.exists("Server Script", name):
                doc = frappe.get_doc("Server Script", name)
                doc.script = body.strip()
                doc.doctype_event = event
                doc.disabled = 0
                doc.save(ignore_permissions=True)
                print(f"  updated {name!r}")
            else:
                frappe.get_doc(payload).insert(ignore_permissions=True)
                print(f"  created {name!r}")
        except Exception as exc:
            print(f"  WARN: could not create {name!r}: {exc}")
    frappe.db.commit()

    # Probe whether Server Scripts will actually execute.
    enabled = bool(
        frappe.local.conf.get("server_script_enabled")
        or frappe.db.get_single_value("System Settings", "developer_mode")
    )
    if not enabled:
        print("\n  !! Server Scripts are saved but will NOT execute --")
        print("     site_config.json has `server_script_enabled: 0` and the")
        print("     site is not in developer mode. Client Script (step 4)")
        print("     enforces the rules in the browser. For server-side")
        print("     hardening, enable Server Scripts via:")
        print("       bench --site sungasmis.v.frappe.cloud set-config")
        print('         server_script_enabled 1')


# --------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------- #
def main():
    print("=" * 78)
    print(" Phase 5.5 -- final fixes (barcode + customer rules)")
    print("=" * 78)

    apply_barcode_fix()
    reverse_customer_group_user_permission()
    set_customer_group_default()
    install_client_script()
    install_server_scripts()

    frappe.clear_cache()
    try:
        frappe.clear_document_cache("Print Format", PRINT_FORMAT_NAME)
    except Exception:
        pass
    frappe.db.commit()

    # ----- Self-test the print again -----
    cand = frappe.db.get_value("POS Invoice", {"docstatus": 1}, "name", order_by="creation desc")
    if cand:
        rendered = frappe.get_print("POS Invoice", cand, print_format=PRINT_FORMAT_NAME, as_pdf=False)
        ok = "SUNGAS COMPANY LIMITED" in rendered
        font_in = "font-family: 'Libre Barcode 128'" in rendered or "Libre Barcode 128" in rendered
        print(f"\n[6] Self-test render against {cand!r}:")
        print(f"    contains 'SUNGAS COMPANY LIMITED'  : {ok}")
        print(f"    references Libre Barcode 128 font  : {font_in}")

    print("\n" + "=" * 78)
    print(" Done. Run:")
    print("     bench --site sungasmis.v.frappe.cloud clear-cache")
    print(" Then hard-refresh the browser and reprint -- barcode should")
    print(" now render as actual bars. Open any Customer record as a")
    print(" cashier to verify view-only + Retail-locked behavior.")
    print("=" * 78)


try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
