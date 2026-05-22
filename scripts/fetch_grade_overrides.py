"""
Fetch /files/grade_overrides.csv from Frappe public files into /tmp/.

After HR uploads the edited CSV via Setup > File > New (Is Private = 0),
run this to copy it to /tmp/ where apply_grade_overrides.py reads it from.

Run:
    curl -fsSL "<raw url>/scripts/fetch_grade_overrides.py" -o /tmp/fetch.py
    bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/fetch.py').read())"
"""

from __future__ import annotations
import shutil
from pathlib import Path
import frappe


SRC = Path(frappe.get_site_path("public", "files", "grade_overrides.csv"))
DST = Path("/tmp/grade_overrides.csv")


def main():
    if not SRC.exists():
        print(f"  ! {SRC} not found.")
        print("    Upload via: ERPNext > Setup > File > New, name=grade_overrides.csv, Is Private=unchecked")
        return
    shutil.copyfile(SRC, DST)
    size = DST.stat().st_size
    print(f"  + copied {SRC} -> {DST} ({size} bytes)")
    # Peek first 5 lines
    print()
    print("  First 5 lines:")
    with DST.open("r", encoding="utf-8-sig") as f:
        for i, line in enumerate(f):
            if i >= 5:
                break
            print(f"    {line.rstrip()}")


try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
