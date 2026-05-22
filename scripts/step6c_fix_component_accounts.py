"""
Phase 6 / Step 6c-FIX: wire missing Salary Component -> Account mappings.

Adds a `Salary Component Account` row (company + account) to the listed
Salary Components. Targeted at the 3 earnings flagged by step6c_audit:
  - Medical Allowance
  - Leave Allowance
  - 13th Month
all of which should debit `9101 - Salary and wages - SCL` (Expense) when
a Salary Slip submits, identical to Basic Pay.

Idempotent: rows that already exist for `COMPANY` are skipped.

Run:
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/feat/sungas-customizations/scripts/step6c_fix_component_accounts.py" -o /tmp/s6c_fix.py
    bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/s6c_fix.py').read())"
"""

from __future__ import annotations
from pathlib import Path
import frappe


DRY_RUN = True

COMPANY = "SUNGAS COMPANY LIMITED"

# (salary_component, target_account)
# Note: Medical Allowance / HMO Benchmark are STATISTICAL (company-borne, slip-only,
# no GL impact) and intentionally have no Account mapping. We wire only the real
# cash earnings here.
MAPPINGS = [
    ("Leave Allowance",   "9101 - Salary and wages - SCL"),
    ("13th Month",        "9101 - Salary and wages - SCL"),
]


def main():
    print("=" * 72)
    print(f" Phase 6 / Step 6c-FIX -- Wire Salary Component Accounts (DRY_RUN={DRY_RUN})")
    print("=" * 72)

    out: list[str] = []
    out.append(f"# Step 6c-FIX -- Salary Component Account wiring (DRY_RUN={DRY_RUN})")
    out.append("")

    for component, account in MAPPINGS:
        if not frappe.db.exists("Salary Component", component):
            out.append(f"  ! Salary Component `{component}` not found -- skipped")
            continue
        if not frappe.db.exists("Account", account):
            out.append(f"  ! Account `{account}` not found -- skipped")
            continue

        existing = frappe.db.get_value(
            "Salary Component Account",
            {"parent": component, "company": COMPANY},
            ["name", "account"],
            as_dict=True,
        )
        if existing:
            if existing["account"] == account:
                out.append(f"  = `{component}` already wired to `{account}`")
            else:
                if DRY_RUN:
                    out.append(f"  ~ would-update `{component}`: `{existing['account']}` -> `{account}`")
                else:
                    frappe.db.set_value("Salary Component Account", existing["name"], "account", account)
                    out.append(f"  ~ `{component}`: `{existing['account']}` -> `{account}`")
            continue

        if DRY_RUN:
            out.append(f"  + would-add `{component}` -> `{account}` (company={COMPANY})")
            continue

        # Append a child row to the Salary Component
        comp_doc = frappe.get_doc("Salary Component", component)
        comp_doc.append("accounts", {
            "company": COMPANY,
            "account": account,
        })
        comp_doc.save(ignore_permissions=True)
        out.append(f"  + `{component}` -> `{account}` (added on Salary Component.accounts)")

    if not DRY_RUN:
        frappe.db.commit()

    p = Path("/tmp/step6c_fix_component_accounts.md")
    p.write_text("\n".join(out), encoding="utf-8")
    print()
    for line in out:
        print(line)
    print()
    print(f"[OK] {p}")
    if DRY_RUN:
        print()
        print("[DRY_RUN] No changes written. Set DRY_RUN=False and re-run to apply.")


try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
