"""
Phase 6 / Step 2d-PROBE: probe ERP for likely matches of unmatched bank-file names.

Read-only. Lists Employee records whose name contains any token that overlaps
with the unmatched HR rows, so you can pick the canonical name.

Run:
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/feat/sungas-customizations/scripts/step2d_probe_unmatched.py" -o /tmp/s2d_probe.py
    bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/s2d_probe.py').read())"
"""

from __future__ import annotations
import frappe


# Names from step2d's "unmatched" list -- and any others to triage
PROBE_NAMES = [
    "IGBINOVA VICTOR",
    "DOMINION ROLAND",
    "BULUS SATI",
]


def main():
    print("=" * 72)
    print(" Phase 6 / Step 2d-PROBE -- search ERP for unmatched bank-file names")
    print("=" * 72)
    for query in PROBE_NAMES:
        print()
        print(f"## {query}")
        tokens = [t for t in query.split() if len(t) > 2]
        for t in tokens:
            rows = frappe.db.sql("""
                select name, employee_name, status, branch
                from tabEmployee
                where employee_name like %s
                order by name
                limit 8
            """, (f"%{t}%",), as_dict=True)
            if not rows:
                continue
            print(f"  token `{t}`:")
            for r in rows:
                print(f"    - {r['name']:<14} {r['employee_name']:<35}  "
                      f"branch=`{r.get('branch') or '-'}`  status={r['status']}")


try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
