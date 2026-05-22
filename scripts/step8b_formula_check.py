"""
Phase 6 / Step 8b-FORMULA-CHECK: dump every formula in Sungas Standard
so we can pinpoint row 6's bug.

Read-only.
"""

from __future__ import annotations
import frappe


STRUCTURE = "Sungas Standard"


def main():
    print("=" * 72)
    print(f" {STRUCTURE} -- Earning + Deduction formulas")
    print("=" * 72)

    ss = frappe.get_doc("Salary Structure", STRUCTURE)

    print()
    print("EARNINGS")
    for i, row in enumerate(ss.earnings, start=1):
        f = (row.formula or "").replace("\n", " \\n ")
        print(f"  row {i:>2} | {row.salary_component:<24} | "
              f"amt={row.amount or 0:<10} | abf={row.amount_based_on_formula} | "
              f"condition={row.condition!r} | formula={f!r}")

    print()
    print("DEDUCTIONS")
    for i, row in enumerate(ss.deductions, start=1):
        f = (row.formula or "").replace("\n", " \\n ")
        print(f"  row {i:>2} | {row.salary_component:<24} | "
              f"amt={row.amount or 0:<10} | abf={row.amount_based_on_formula} | "
              f"condition={row.condition!r} | formula={f!r}")


try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
