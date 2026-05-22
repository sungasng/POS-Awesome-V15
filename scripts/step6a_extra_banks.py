"""
Phase 6 / Step 6a-EXTRA: seed two banks not in the original Tier-1 list.

Adds:
  - PAYCOM (OPAY)     -- NIBSS code 100004 (Payment Service Bank / fintech)
  - Parallex Bank     -- NIBSS code 000030 (commercial)

Idempotent. Safe to re-run.

Run:
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/feat/sungas-customizations/scripts/step6a_extra_banks.py" -o /tmp/s6a_extra.py
    bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/s6a_extra.py').read())"
"""

from __future__ import annotations
import frappe


EXTRA_BANKS = [
    # (canonical name, nibss_code, category)
    ("OPAY",          "100004", "Payment Service Bank"),
    ("Parallex Bank", "000030", "Commercial Bank"),
]


def main():
    print("=" * 72)
    print(" Phase 6 / Step 6a-EXTRA -- Seed OPAY + Parallex Bank")
    print("=" * 72)

    for name, nibss, category in EXTRA_BANKS:
        if frappe.db.exists("Bank", name):
            cur_code = frappe.db.get_value("Bank", name, "nibss_code")
            if cur_code != nibss:
                frappe.db.set_value("Bank", name, "nibss_code", nibss)
                print(f"  ~ updated `{name}` nibss_code: {cur_code!r} -> {nibss!r}")
            else:
                print(f"  = `{name}` already seeded ({nibss})")
            continue
        doc = frappe.get_doc({
            "doctype": "Bank",
            "bank_name": name,
            "nibss_code": nibss,
        })
        if frappe.get_meta("Bank").has_field("bank_category"):
            doc.bank_category = category
        doc.insert(ignore_permissions=True)
        print(f"  + created `{name}` (NIBSS {nibss}, {category})")

    frappe.db.commit()
    print()
    print(f"  Total Banks seeded with NIBSS code: "
          f"{frappe.db.count('Bank', {'nibss_code': ['is', 'set']})}")


try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
