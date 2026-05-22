"""
Phase 6 / Step 6c-SWAP: re-point Company.default_payroll_payable_account
from the auto-created orphan to the canonical CoA account, and clean up.

Actions (idempotent):
    1. Set Account.account_type = 'Payable' on `CANONICAL_ACCOUNT` (Frappe
       requires account_type='Payable' for any account used as
       payroll_payable_account).
    2. Set Company.default_payroll_payable_account = `CANONICAL_ACCOUNT`.
    3. Delete the orphan `ORPHAN_ACCOUNT` (only if 0 GL entries on it).
       If GL entries exist, just disable it.

DRY_RUN=True   -> print plan, no writes.
DRY_RUN=False  -> commit changes.

Run:
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/feat/sungas-customizations/scripts/step6c_swap_payable.py" -o /tmp/s6c_swap.py
    bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/s6c_swap.py').read())"
"""

from __future__ import annotations
from pathlib import Path
import frappe


DRY_RUN = True

COMPANY            = "SUNGAS COMPANY LIMITED"
CANONICAL_ACCOUNT  = "6207 - Salary Control Account - SCL"
ORPHAN_ACCOUNT     = "Salary Payable - SCL"


def main():
    print("=" * 72)
    print(f" Phase 6 / Step 6c-SWAP -- Re-point Payroll Payable (DRY_RUN={DRY_RUN})")
    print("=" * 72)

    out: list[str] = []
    out.append(f"# Step 6c-SWAP -- Repoint Payroll Payable (DRY_RUN={DRY_RUN})")
    out.append("")
    out.append(f"_Generated: {frappe.utils.now_datetime()} | Site: {frappe.local.site}_")
    out.append("")

    # 0. Validate prerequisites
    if not frappe.db.exists("Account", CANONICAL_ACCOUNT):
        msg = f"  ! Canonical account `{CANONICAL_ACCOUNT}` not found. Aborting."
        print(msg)
        return
    canon = frappe.db.get_value(
        "Account", CANONICAL_ACCOUNT,
        ["name", "account_type", "is_group", "disabled", "company", "root_type"],
        as_dict=True,
    )
    if canon["is_group"]:
        print(f"  ! `{CANONICAL_ACCOUNT}` is a group account. Pick a leaf.")
        return
    if canon["disabled"]:
        print(f"  ! `{CANONICAL_ACCOUNT}` is disabled. Re-enable in Desk first.")
        return
    if canon["company"] != COMPANY:
        print(f"  ! `{CANONICAL_ACCOUNT}` belongs to company {canon['company']!r}, not {COMPANY!r}. Aborting.")
        return
    if canon["root_type"] != "Liability":
        print(f"  ! `{CANONICAL_ACCOUNT}` root_type={canon['root_type']!r} (expected Liability). Aborting.")
        return

    out.append(f"  Canonical: `{CANONICAL_ACCOUNT}` (current account_type={canon['account_type']!r})")
    out.append(f"  Orphan   : `{ORPHAN_ACCOUNT}`")
    out.append("")

    # 1. Ensure account_type=Payable on canonical
    out.append("## 1. Force account_type='Payable' on canonical")
    out.append("")
    if canon["account_type"] == "Payable":
        out.append("  = already Payable")
    else:
        if DRY_RUN:
            out.append(f"  + would-set Account.account_type='Payable' on `{CANONICAL_ACCOUNT}`")
        else:
            frappe.db.set_value("Account", CANONICAL_ACCOUNT, "account_type", "Payable")
            out.append(f"  + Account.account_type='Payable' on `{CANONICAL_ACCOUNT}`")
    out.append("")

    # 2. Repoint Company default
    out.append("## 2. Company.default_payroll_payable_account")
    out.append("")
    current = frappe.db.get_value("Company", COMPANY, "default_payroll_payable_account")
    out.append(f"  current : `{current}`")
    if current == CANONICAL_ACCOUNT:
        out.append("  = already pointing to canonical")
    else:
        if DRY_RUN:
            out.append(f"  + would-set Company.default_payroll_payable_account = `{CANONICAL_ACCOUNT}`")
        else:
            frappe.db.set_value("Company", COMPANY, "default_payroll_payable_account", CANONICAL_ACCOUNT)
            out.append(f"  + Company.default_payroll_payable_account = `{CANONICAL_ACCOUNT}`")
    out.append("")

    # 3. Clean up orphan
    out.append("## 3. Orphan cleanup")
    out.append("")
    if not frappe.db.exists("Account", ORPHAN_ACCOUNT):
        out.append(f"  = `{ORPHAN_ACCOUNT}` does not exist (already cleaned).")
    else:
        gl_count = frappe.db.count("GL Entry", {"account": ORPHAN_ACCOUNT})
        out.append(f"  GL Entries on orphan: {gl_count}")
        if gl_count == 0:
            if DRY_RUN:
                out.append(f"  + would-delete `{ORPHAN_ACCOUNT}` (0 GL entries)")
            else:
                try:
                    frappe.delete_doc("Account", ORPHAN_ACCOUNT, ignore_permissions=True, force=1)
                    out.append(f"  + deleted `{ORPHAN_ACCOUNT}`")
                except Exception as e:
                    # If delete blocked, fall back to disable
                    frappe.db.set_value("Account", ORPHAN_ACCOUNT, "disabled", 1)
                    out.append(f"  ~ delete blocked ({e!s}); marked as disabled instead")
        else:
            if DRY_RUN:
                out.append(f"  + would-disable `{ORPHAN_ACCOUNT}` (has {gl_count} GL entries)")
            else:
                frappe.db.set_value("Account", ORPHAN_ACCOUNT, "disabled", 1)
                out.append(f"  + disabled `{ORPHAN_ACCOUNT}` (has {gl_count} GL entries)")
    out.append("")

    if not DRY_RUN:
        frappe.db.commit()

    p = Path("/tmp/step6c_swap_payable.md")
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
