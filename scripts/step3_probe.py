"""
Phase 6 / Step 3 PROBE: discover rent fields + director designations + PAYE STUB.

Run:
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/feat/sungas-customizations/scripts/step3_probe.py" -o /tmp/step3_probe.py
    bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/step3_probe.py').read())"
"""

from __future__ import annotations
import frappe


def main():
    print("=" * 72)
    print(" PHASE 6 / STEP 3 PROBE")
    print("=" * 72)

    print()
    print("=== 1. Employee rent / housing / accommodation fields ===")
    custom = frappe.get_all(
        "Custom Field",
        filters={"dt": "Employee"},
        fields=["fieldname", "label", "fieldtype"],
    )
    found_any = False
    for fld in custom:
        haystack = (fld["fieldname"] + " " + (fld.get("label") or "")).lower()
        if any(k in haystack for k in ("rent", "hous", "accom")):
            print(f"  custom: {fld['fieldname']:35s} | {fld['label']:40s} | {fld['fieldtype']}")
            found_any = True
    meta = frappe.get_meta("Employee")
    for df in meta.fields:
        haystack = (df.fieldname + " " + (df.label or "")).lower()
        if any(k in haystack for k in ("rent", "hous", "accom")):
            print(f"  std:    {df.fieldname:35s} | {(df.label or ''):40s} | {df.fieldtype}")
            found_any = True
    if not found_any:
        print("  (none found)")

    print()
    print("=== 2. Director-like designations (Active employees) ===")
    desigs = frappe.db.sql(
        """
        select designation, count(*) as n
        from tabEmployee
        where status='Active'
          and (
              designation like '%Director%'
              or designation like '%Chairman%'
              or designation like '%Executive%'
              or designation like '%Independent%'
          )
        group by designation
        order by n desc
        """,
        as_dict=1,
    )
    if desigs:
        for d in desigs:
            print(f"  {d['n']:3d} x  {d['designation']}")
    else:
        print("  (none)")

    print()
    print("=== 3. PAYE Salary Component (current STUB) ===")
    if frappe.db.exists("Salary Component", "PAYE"):
        sc = frappe.get_doc("Salary Component", "PAYE")
        print(f"  abbr:                   {sc.salary_component_abbr}")
        print(f"  amount_based_on_formula:{sc.amount_based_on_formula}")
        print(f"  type:                   {sc.type}")
        print(f"  statistical_component:  {getattr(sc, 'statistical_component', None)}")
        print()
        print(f"  condition: {sc.condition!r}")
        print()
        print("  formula:")
        for line in (sc.formula or "").splitlines():
            print(f"    {line}")
    else:
        print("  PAYE component NOT FOUND")

    print()
    print("=== 4. All Salary Components on Sungas Standard structure ===")
    if frappe.db.exists("Salary Structure", "Sungas Standard"):
        ss = frappe.get_doc("Salary Structure", "Sungas Standard")
        print("  Earnings:")
        for row in ss.earnings:
            print(f"    {row.salary_component:35s} ({row.abbr})  formula={(row.formula or '')[:50]}")
        print("  Deductions:")
        for row in ss.deductions:
            print(f"    {row.salary_component:35s} ({row.abbr})  formula={(row.formula or '')[:50]}")
    else:
        print("  Sungas Standard structure not found")

    print()
    print("=== 5. Sample employees for dry-run validation (5 reps across pay bands) ===")
    sample = frappe.db.sql(
        """
        select e.name, e.employee_name, e.designation, e.department, ssa.base
        from tabEmployee e
        join `tabSalary Structure Assignment` ssa on ssa.employee=e.name
        where e.status='Active'
          and ssa.salary_structure='Sungas Standard'
          and ssa.docstatus=1
        order by ssa.base
        """,
        as_dict=1,
    )
    if sample:
        bands = [sample[0]]
        for pct in (0.25, 0.5, 0.75):
            bands.append(sample[int(len(sample) * pct)])
        bands.append(sample[-1])
        for s in bands:
            print(f"  base={s['base']:>14,.2f}  {s['name']}  {s['employee_name']:30s}  desig={s['designation']!r}")
    print()


try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
