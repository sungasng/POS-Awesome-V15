"""
p57: Temporarily unlock the period by clearing stock_frozen_upto and
acc_frozen_upto. Used to recover from "locked too early" situations where
same-day activity got trapped inside the freeze window.

Parameters (env vars):
    LIVE        "1" to write. Default "0" (dry-run).
    TARGET      Date string to set freeze TO (default "0001-01-01" = fully unlocked).
                Examples: "0001-01-01" (off), "2026-04-30" (only April locked).

Read-only by default.
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime
import os
import frappe


def main():
    L = []
    p = L.append
    live = os.environ.get("LIVE", "0") == "1"
    # Safe distant-past date (Python date can't represent year 0001 cleanly, and
    # writing it via doc.save() causes Frappe to store NULL, which then breaks
    # ERPNext's check_stock_frozen_date() comparison). 1900-01-01 is the lowest
    # safe value.
    target = os.environ.get("TARGET", "1900-01-01").strip()

    p("# p57: Temporarily unlock period (revert freeze dates)")
    p("")
    p(f"- Mode: {'LIVE (will write)' if live else 'DRY-RUN (no writes)'}")
    p(f"- Target freeze date: `{target}`")
    p(f"- Run as: `{frappe.session.user}` at `{datetime.utcnow().isoformat()}Z`")
    p("")

    stock_cur = frappe.db.get_single_value("Stock Settings", "stock_frozen_upto") or ""
    acc_cur = frappe.db.get_single_value("Accounts Settings", "acc_frozen_upto") or ""
    p("## Current freeze dates")
    p(f"- `Stock Settings.stock_frozen_upto` = `{stock_cur}`")
    p(f"- `Accounts Settings.acc_frozen_upto` = `{acc_cur}`")
    p("")

    p("## Planned change")
    p(f"- stock_frozen_upto: `{stock_cur}` -> `{target}`")
    p(f"- acc_frozen_upto:   `{acc_cur}` -> `{target}`")
    p("")

    if not live:
        p("## DRY-RUN -- no changes made")
        p("Re-run with `LIVE=1` to apply.")
        _save(L)
        return

    p("## Applying changes")
    try:
        ss = frappe.get_doc("Stock Settings")
        ss.stock_frozen_upto = target
        ss.save(ignore_permissions=True)
        p(f"- stock_frozen_upto set to `{target}`")
    except Exception as e:
        p(f"- :x: stock_frozen_upto failed: {e}")
        _save(L)
        return
    try:
        ag = frappe.get_doc("Accounts Settings")
        ag.acc_frozen_upto = target
        ag.save(ignore_permissions=True)
        p(f"- acc_frozen_upto set to `{target}`")
    except Exception as e:
        p(f"- :x: acc_frozen_upto failed: {e}")
        _save(L)
        return

    frappe.db.commit()
    p("- COMMITTED.")
    p("")

    new_stock = frappe.db.get_single_value("Stock Settings", "stock_frozen_upto") or ""
    new_acc = frappe.db.get_single_value("Accounts Settings", "acc_frozen_upto") or ""
    p("## Verification")
    p(f"- `Stock Settings.stock_frozen_upto` = `{new_stock}`")
    p(f"- `Accounts Settings.acc_frozen_upto` = `{new_acc}`")
    ok = str(new_stock) == target and str(new_acc) == target
    p(f"- **{'OK' if ok else 'MISMATCH'}**")

    _save(L)


def _save(L):
    out = "\n".join(L)
    Path("/tmp/p57_unlock.log").write_text(out, encoding="utf-8")
    print(out)
    print()
    print("  Log: /tmp/p57_unlock.log")


main()
