"""
Diagnostic: list every Role Profile and every Role whose name starts with
'LPG' so we can confirm what actually exists on the site before assigning
cashier permissions.

Run on bench:
    curl -fsSL https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/feat/sungas-customizations/scripts/list_lpg_roles.py \
      -o /tmp/list_lpg_roles.py && \
    bench --site sungasmis.v.frappe.cloud execute \
      "exec(open('/tmp/list_lpg_roles.py').read())"
"""

from __future__ import annotations

import frappe


def main():
    print("=" * 78)
    print(" LPG Role / Role Profile diagnostic")
    print("=" * 78)

    print("\n[1] All Role Profiles on the site:")
    profiles = frappe.get_all(
        "Role Profile", fields=["name"], order_by="name"
    )
    if not profiles:
        print("    (none)")
    for p in profiles:
        roles = frappe.get_all(
            "Has Role",
            filters={"parent": p.name, "parenttype": "Role Profile"},
            fields=["role"],
        )
        role_names = ", ".join(sorted(r.role for r in roles)) or "<empty>"
        print(f"    - {p.name!r}  ({len(roles)} roles)  -> {role_names}")

    print("\n[2] All Roles whose name contains 'LPG' or 'POS':")
    roles = frappe.get_all(
        "Role",
        filters=[["name", "like", "%LPG%"]],
        fields=["name", "disabled"],
        order_by="name",
    )
    roles += frappe.get_all(
        "Role",
        filters=[["name", "like", "%POS%"]],
        fields=["name", "disabled"],
        order_by="name",
    )
    seen = set()
    for r in roles:
        if r.name in seen:
            continue
        seen.add(r.name)
        flag = " (disabled)" if r.disabled else ""
        print(f"    - {r.name!r}{flag}")
    if not seen:
        print("    (none)")

    print("\n[3] Probe specific candidates:")
    for n in (
        "LPG POS User", "LPG Plant Manager",
        "LPG Head of Sales", "LPG Head of Finance",
    ):
        rp = frappe.db.exists("Role Profile", n)
        role = frappe.db.exists("Role", n)
        print(f"    - {n!r:30}  RoleProfile={'YES' if rp else 'no '}  Role={'YES' if role else 'no '}")


try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
