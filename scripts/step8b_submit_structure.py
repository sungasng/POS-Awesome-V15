"""
Phase 6 / Step 8b -- SUBMIT the 'Sungas Standard' Salary Structure.

The structure was in DRAFT (docstatus=0), so HRMS's `check_sal_struct` /
`get_sal_struct` queries returned no rows (they filter `ss.docstatus=1`),
which is what caused all 216 slip inserts to fail with
"Please assign a Salary Structure for Employee X applicable from or before
01-05-2026 first".

This script:
  1. Looks up the structure
  2. If docstatus=0, submits it
  3. If docstatus=2 (Cancelled), creates an amended copy and submits
  4. Prints final docstatus + a quick filter probe so we can verify HRMS is happy

Run:
    SHA=<sha>
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/$SHA/scripts/step8b_submit_structure.py" -o /tmp/s8b_submit.py
    bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/s8b_submit.py').read())"
"""

from __future__ import annotations
import frappe


STRUCTURE_NAME = "Sungas Standard"


def main() -> None:
    print("=" * 72)
    print(f" Submit Salary Structure: {STRUCTURE_NAME}")
    print("=" * 72)

    if not frappe.db.exists("Salary Structure", STRUCTURE_NAME):
        print(f"  ! Structure '{STRUCTURE_NAME}' not found")
        return

    ss = frappe.get_doc("Salary Structure", STRUCTURE_NAME)
    print(f"  Before:  docstatus={ss.docstatus}  is_active={ss.is_active!r}  "
          f"freq={ss.payroll_frequency!r}  currency={ss.currency!r}")

    if ss.docstatus == 1:
        print("  = Already submitted -- no action needed.")
    elif ss.docstatus == 0:
        try:
            ss.flags.ignore_permissions = True
            ss.submit()
            frappe.db.commit()
            print(f"  + SUBMITTED. docstatus is now {ss.docstatus}")
        except Exception as e:
            print(f"  ! submit() failed: {e!r}")
            # Print last frappe error log if available
            import traceback
            traceback.print_exc()
            return
    elif ss.docstatus == 2:
        # Cancelled -- need to amend
        try:
            from frappe.model.workflow import get_workflow_name  # noqa: F401
            new = frappe.copy_doc(ss)
            new.amended_from = ss.name
            new.docstatus = 0
            new.flags.ignore_permissions = True
            new.insert()
            new.submit()
            frappe.db.commit()
            print(f"  + AMENDED. New name: {new.name}")
            print("  ! WARNING: SSAs still reference old structure name. "
                  "Need follow-up script to repoint SSAs.")
        except Exception as e:
            print(f"  ! amend failed: {e!r}")
            import traceback
            traceback.print_exc()
            return

    # ---- Verify HRMS filter is now satisfied ----
    n = frappe.db.sql("""
        select count(*) from `tabSalary Structure`
        where name = %s and docstatus = 1 and is_active = 'Yes'
          and payroll_frequency = 'Monthly' and currency = 'NGN'
    """, STRUCTURE_NAME)[0][0]
    print()
    if n == 1:
        print(f"  = HRMS visibility check: '{STRUCTURE_NAME}' is now visible to PE filter. PASS.")
    else:
        print(f"  ! HRMS visibility check: still 0 rows match. count={n}")


# bench execute scope-fix
try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
