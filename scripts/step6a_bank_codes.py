"""
Phase 6 / Step 6a: Seed Frappe Bank doctype with Nigerian banks + NIBSS codes.

Adds custom field `Bank.nibss_code` (Data, 6 digits) so the bank-upload
generator can look it up at runtime.

Source: Sungas-supplied NIBSS bank list (June 2026).

Run:
    curl -fsSL "<raw url>/scripts/step6a_bank_codes.py" -o /tmp/s6a.py
    bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/s6a.py').read())"
"""

from __future__ import annotations
from pathlib import Path
import frappe


DRY_RUN = False


# Subset of banks Sungas staff are likely to use (Tier 1 commercial banks).
# Full PSB / MFB list can be added later via UI bulk import if needed.
BANKS = [
    # (name, nibss_code, category)
    ("Sterling Bank",                         "000001", "Commercial Bank"),
    ("Keystone Bank",                         "000002", "Commercial Bank"),
    ("FCMB",                                  "000003", "Commercial Bank"),
    ("United Bank for Africa",                "000004", "Commercial Bank"),
    ("JAIZ Bank",                             "000006", "Commercial Bank"),
    ("Fidelity Bank",                         "000007", "Commercial Bank"),
    ("Polaris Bank",                          "000008", "Commercial Bank"),
    ("Citi Bank",                             "000009", "Commercial Bank"),
    ("Ecobank Bank",                          "000010", "Commercial Bank"),
    ("Unity Bank",                            "000011", "Commercial Bank"),
    ("StanbicIBTC Bank",                      "000012", "Commercial Bank"),
    ("GTBank Plc",                            "000013", "Commercial Bank"),
    ("Access Bank",                           "000014", "Commercial Bank"),
    ("Zenith Bank Plc",                       "000015", "Commercial Bank"),
    ("First Bank of Nigeria",                 "000016", "Commercial Bank"),
    ("Wema Bank",                             "000017", "Commercial Bank"),
    ("Union Bank",                            "000018", "Commercial Bank"),
    ("Heritage Bank",                         "000020", "Commercial Bank"),
    ("Standard Chartered",                    "000021", "Commercial Bank"),
    ("Suntrust Bank",                         "000022", "Commercial Bank"),
    ("Providus Bank",                         "000023", "Commercial Bank"),
    ("Titan Trust Bank",                      "000025", "Commercial Bank"),
    ("Taj Bank",                              "000026", "Commercial Bank"),
    ("Globus Bank",                           "000027", "Commercial Bank"),
    ("Lotus Bank",                            "000029", "Commercial Bank"),
    ("Premium Trust Bank",                    "000031", "Commercial Bank"),
    ("Signature Bank",                        "000034", "Commercial Bank"),
    ("Optimus Bank",                          "000036", "Commercial Bank"),
    ("Parallex Bank",                         "000030", "Commercial Bank"),
    # Popular fintech / PSBs
    ("Kuda Microfinance Bank",                "090267", "Microfinance Bank"),
    ("Moniepoint Microfinance Bank",          "090405", "Microfinance Bank"),
    ("Paycom (Opay)",                         "100004", "Payment Service Bank"),
    ("PalmPay Limited",                       "100033", "Payment Service Bank"),
    ("9Payment Service Bank",                 "120001", "Payment Service Bank"),
    ("HopePSB",                               "120002", "Payment Service Bank"),
    ("MoMo PSB",                              "120003", "Payment Service Bank"),
    ("SmartCash PSB",                         "120004", "Payment Service Bank"),
    ("VFD MFB",                               "090110", "Microfinance Bank"),
    ("FairMoney Microfinance Bank",           "090551", "Microfinance Bank"),
    ("Sparkle",                               "090325", "Microfinance Bank"),
    ("Eyowo",                                 "090328", "Microfinance Bank"),
    ("Rubies (Highstreet) Microfinance Bank", "090175", "Microfinance Bank"),
    ("LAPO Microfinance Bank",                "090177", "Microfinance Bank"),
    ("Accion Microfinance Bank",              "090134", "Microfinance Bank"),
    ("NPF MicroFinance Bank",                 "070001", "Microfinance Bank"),
]


def add_nibss_code_field(report: list[str]) -> None:
    report.append("## 1. Custom field Bank.nibss_code")
    report.append("")
    cf_name = "Bank-nibss_code"
    if frappe.db.exists("Custom Field", cf_name):
        report.append("  = already exists")
        report.append("")
        return
    if DRY_RUN:
        report.append("  + would-insert (Data, 6 chars, unique-not-enforced)")
        report.append("")
        return
    frappe.get_doc({
        "doctype": "Custom Field",
        "dt": "Bank",
        "fieldname": "nibss_code",
        "label": "NIBSS Code",
        "fieldtype": "Data",
        "length": 6,
        "in_list_view": 1,
        "in_standard_filter": 1,
        "insert_after": "swift_number",
        "description": "6-digit NIBSS sort code used in inter-bank transfer files.",
    }).insert(ignore_permissions=True, ignore_if_duplicate=True)
    report.append("  + inserted")
    report.append("")


def add_category_field(report: list[str]) -> None:
    report.append("## 2. Custom field Bank.bank_category")
    report.append("")
    cf_name = "Bank-bank_category"
    if frappe.db.exists("Custom Field", cf_name):
        report.append("  = already exists")
        report.append("")
        return
    if DRY_RUN:
        report.append("  + would-insert (Select)")
        report.append("")
        return
    frappe.get_doc({
        "doctype": "Custom Field",
        "dt": "Bank",
        "fieldname": "bank_category",
        "label": "Category",
        "fieldtype": "Select",
        "options": "\nCommercial Bank\nMicrofinance Bank\nPayment Service Bank\nMortgage Bank\nMerchant Bank\nDevelopment Bank",
        "in_list_view": 1,
        "in_standard_filter": 1,
        "insert_after": "nibss_code",
    }).insert(ignore_permissions=True, ignore_if_duplicate=True)
    report.append("  + inserted")
    report.append("")


def seed_banks(report: list[str]) -> None:
    report.append("## 3. Seed Bank records")
    report.append("")
    created = 0
    updated = 0
    skipped = 0
    for name, code, category in BANKS:
        if frappe.db.exists("Bank", name):
            current_code = frappe.db.get_value("Bank", name, "nibss_code")
            current_cat = frappe.db.get_value("Bank", name, "bank_category")
            if current_code == code and current_cat == category:
                skipped += 1
                continue
            if DRY_RUN:
                report.append(f"  ~ would-update `{name}` (code: {current_code} -> {code})")
                updated += 1
                continue
            frappe.db.set_value("Bank", name, "nibss_code", code)
            frappe.db.set_value("Bank", name, "bank_category", category)
            updated += 1
            continue
        if DRY_RUN:
            report.append(f"  + would-create `{name}` (code={code}, {category})")
            created += 1
            continue
        frappe.get_doc({
            "doctype": "Bank",
            "bank_name": name,
            "nibss_code": code,
            "bank_category": category,
        }).insert(ignore_permissions=True, ignore_if_duplicate=True)
        created += 1

    report.append(f"  Created: {created}")
    report.append(f"  Updated: {updated}")
    report.append(f"  No-change: {skipped}")
    report.append("")


def main():
    print("=" * 72)
    print(f" Phase 6 / Step 6a -- Bank seed + NIBSS codes (DRY_RUN={DRY_RUN})")
    print("=" * 72)

    report: list[str] = []
    report.append("# Step 6a -- Bank doctype seed")
    report.append("")
    report.append(f"_Generated: {frappe.utils.now_datetime()} | Site: {frappe.local.site} | DRY_RUN={DRY_RUN}_")
    report.append("")

    add_nibss_code_field(report)
    add_category_field(report)
    seed_banks(report)

    if not DRY_RUN:
        frappe.db.commit()

    p = Path("/tmp/step6a_banks.md")
    p.write_text("\n".join(report), encoding="utf-8")
    print(f"\n[OK] wrote {p}\n")
    for line in report:
        print(line)


try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
