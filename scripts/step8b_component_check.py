"""
Phase 6 / Step 8b-COMPONENT-CHECK: dump Salary Component-level
formula + condition for components used in Sungas Standard.

Read-only.
"""

from __future__ import annotations
import frappe


COMPONENTS = [
    "Basic Pay", "Transport Allowance", "Housing Allowance",
    "Cost of Living Allowance", "Medical Allowance", "Leave Allowance",
    "13th Month", "NSITF", "Pension Employee", "Pension Employer",
    "PAYE", "HMO Top-up (Staff Paid)", "Loan Repayment",
    "COOP Loan Repayment", "Cooperative Contribution",
]


def main():
    print("=" * 72)
    print(" Salary Component-level formula + condition")
    print("=" * 72)
    for name in COMPONENTS:
        if not frappe.db.exists("Salary Component", name):
            print(f"  ! `{name}` not found")
            continue
        c = frappe.get_doc("Salary Component", name)
        f = (c.formula or "").replace("\n", " \\n ")
        cond = (c.condition or "").replace("\n", " \\n ")
        print(f"  {name:<28} | abbr={c.salary_component_abbr or '-':<6} | "
              f"type={c.type or '-':<10} | abf={c.amount_based_on_formula} | "
              f"stat={getattr(c, 'statistical_component', 0)} | "
              f"formula={f!r:<70} | condition={cond!r}")


try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
