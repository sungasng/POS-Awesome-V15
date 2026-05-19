"""
Phase 6 / Step 2c.3b: Submit any leftover draft Salary Structure Assignments.

The main step2c.3 script only submits brand-NEW SSAs. If a prior partial run
left 8 drafts behind (saved but not submitted), this one-liner cleans them up.

Run:
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/feat/sungas-customizations/scripts/step2c3b_submit_draft_ssas.py" -o /tmp/step2c3b.py
    bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/step2c3b.py').read())"
"""

from __future__ import annotations
import frappe


def main():
    drafts = frappe.get_all(
        "Salary Structure Assignment",
        filters={"salary_structure": "Sungas Standard", "docstatus": 0},
        fields=["name", "employee", "employee_name", "base", "from_date"],
    )
    print(f"Found {len(drafts)} draft SSA(s) on 'Sungas Standard'")
    submitted = 0
    errors = []
    for d in drafts:
        try:
            doc = frappe.get_doc("Salary Structure Assignment", d["name"])
            doc.submit()
            submitted += 1
            print(f"  + submitted {d['name']:50s}  emp={d['employee']}  base={d['base']:>12,.2f}")
        except Exception as e:
            errors.append((d["name"], str(e)))
            print(f"  ! {d['name']}: {e}")
    frappe.db.commit()
    print()
    print(f"Submitted: {submitted} / {len(drafts)}")
    if errors:
        print(f"Errors: {len(errors)}")


try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
