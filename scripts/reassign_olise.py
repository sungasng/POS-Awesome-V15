"""
One-off: Reassign HR-EMP-00026 (OLISE Ochonogor) to Operations / Headquarters.

Current state: department='Depot Representative' (probably), branch=<outlet>
Desired state: department='Operations', branch='Headquarters'
                payroll_cost_center='70013 - Operations Headquarters - SCL'

Run:
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/feat/sungas-customizations/scripts/reassign_olise.py" -o /tmp/olise.py
    bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/olise.py').read())"
"""

from __future__ import annotations
import frappe


EMP_ID = "HR-EMP-00026"
TARGET_DEPT_LIKE = "Operations"      # match the existing 'Operations' department record
TARGET_BRANCH = "Headquarters"       # existing Branch
TARGET_CC_PREFIX = "70013"           # 70013 - Operations Headquarters - SCL


def find_dept_by_keyword(keyword: str) -> str | None:
    rows = frappe.get_all(
        "Department",
        filters={"name": ["like", f"%{keyword}%"]},
        fields=["name"],
    )
    # Prefer exact match
    exact = [r["name"] for r in rows if keyword.lower() in r["name"].lower() and "head" not in r["name"].lower()]
    if exact:
        return exact[0]
    return rows[0]["name"] if rows else None


def find_cc(prefix: str) -> str | None:
    rows = frappe.get_all(
        "Cost Center",
        filters={"is_group": 0, "name": ["like", f"{prefix} -%"]},
        fields=["name"],
        limit=1,
    )
    return rows[0]["name"] if rows else None


def main():
    print("=" * 60)
    print(f" Reassign {EMP_ID} -> Operations / Headquarters")
    print("=" * 60)

    if not frappe.db.exists("Employee", EMP_ID):
        print(f"  ! Employee {EMP_ID} not found")
        return

    emp = frappe.get_doc("Employee", EMP_ID)
    print(f"\n  Current: name={emp.employee_name!r}")
    print(f"           department={emp.department!r}")
    print(f"           designation={emp.designation!r}")
    print(f"           branch={emp.branch!r}")
    print(f"           payroll_cost_center={emp.get('payroll_cost_center')!r}")

    target_dept = find_dept_by_keyword(TARGET_DEPT_LIKE)
    target_cc = find_cc(TARGET_CC_PREFIX)

    print(f"\n  Target:  department={target_dept!r}")
    print(f"           branch={TARGET_BRANCH!r}")
    print(f"           payroll_cost_center={target_cc!r}")

    if not target_dept:
        print("\n  ! No Operations department found -- abort")
        return
    if not frappe.db.exists("Branch", TARGET_BRANCH):
        print(f"\n  ! Branch '{TARGET_BRANCH}' not found -- abort")
        return
    if not target_cc:
        print(f"\n  ! Cost Center starting with '{TARGET_CC_PREFIX}' not found -- abort")
        return

    changes = []
    if emp.department != target_dept:
        changes.append(f"department: {emp.department!r} -> {target_dept!r}")
        emp.department = target_dept
    if emp.branch != TARGET_BRANCH:
        changes.append(f"branch: {emp.branch!r} -> {TARGET_BRANCH!r}")
        emp.branch = TARGET_BRANCH
    if emp.get("payroll_cost_center") != target_cc:
        changes.append(f"payroll_cost_center: {emp.get('payroll_cost_center')!r} -> {target_cc!r}")
        emp.payroll_cost_center = target_cc

    if not changes:
        print("\n  = no changes needed")
        return

    print("\n  Applying:")
    for c in changes:
        print(f"    - {c}")
    emp.save(ignore_permissions=True)
    frappe.db.commit()
    print(f"\n  ✓ saved {EMP_ID}")


try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
