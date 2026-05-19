"""
One-off: Toggle Employee.eligible_for_13th_month globally.

Use when management decides to enable/disable the December 13th-month payout
across the entire company in response to year's financial performance.

Edit ENABLE below and run:
    bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/toggle.py').read())"
"""

from __future__ import annotations
import frappe


ENABLE = True   # True = pay 13th month in Dec; False = skip this year
DRY_RUN = False


def main():
    val = 1 if ENABLE else 0
    employees = frappe.get_all(
        "Employee",
        filters={"status": "Active"},
        fields=["name", "eligible_for_13th_month"],
    )
    print("=" * 60)
    print(f" Toggle eligible_for_13th_month -> {val} ({len(employees)} employees)")
    print(f" DRY_RUN={DRY_RUN}")
    print("=" * 60)

    changes = 0
    for emp in employees:
        if (emp.get("eligible_for_13th_month") or 0) != val:
            if not DRY_RUN:
                frappe.db.set_value("Employee", emp["name"], "eligible_for_13th_month", val)
            changes += 1

    if not DRY_RUN:
        frappe.db.commit()

    print(f"\n  Changed: {changes}")
    print(f"  Already in target state: {len(employees) - changes}")


try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
