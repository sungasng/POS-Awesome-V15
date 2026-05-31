"""
p57: Recovery script for the NULL-freeze-date / orphaned-closing-shift situation.

Background:
  Setting freeze_date to "0001-01-01" via doc.save() caused Frappe to store
  NULL (Python date can't represent year 0001). ERPNext's
  check_stock_frozen_date() then errors with TypeError comparing date<=None.
  Meanwhile a draft POS Closing Shift (POSA-CS-26-0000002) was already inserted
  before the submit blew up.

What this does:
  1. Force-writes freeze dates DIRECTLY via SQL to a real, safe date string
     "1900-01-01" (well before any business activity, but a valid Python date).
     This bypasses doc.save() altogether.
  2. Re-fetches the draft POS Closing Shift and submits it (the same merge-log
     consolidation will re-run on submit, this time without the freeze fault).
  3. Verifies the Opening Shift status flipped to Closed.

Parameters:
    LIVE        "1" to write. Default "0".
    DRAFT_CS    Closing-shift doc name to submit. Default POSA-CS-26-0000002.
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime
import os
import frappe


SAFE_DATE = "1900-01-01"


def main():
    L = []
    p = L.append
    live = os.environ.get("LIVE", "0") == "1"
    draft = os.environ.get("DRAFT_CS", "POSA-CS-26-0000002")

    p("# p57: Recover from NULL freeze dates + submit stuck POS Closing Shift")
    p("")
    p(f"- Mode: {'LIVE (will write)' if live else 'DRY-RUN (no writes)'}")
    p(f"- Draft Closing Shift to submit: `{draft}`")
    p(f"- Safe freeze date to write: `{SAFE_DATE}`")
    p(f"- Run as: `{frappe.session.user}` at `{datetime.utcnow().isoformat()}Z`")
    p("")

    # 1. Show current values (raw SQL to expose NULL vs empty)
    p("## 1. Current freeze dates (raw SQL)")
    s = frappe.db.sql(
        "select name, field, ifnull(value, '<NULL>') as v "
        "from `tabSingles` "
        "where (doctype, field) in (('Stock Settings','stock_frozen_upto'),"
        "                            ('Accounts Settings','acc_frozen_upto'))",
        as_dict=True,
    )
    if not s:
        p("- (no rows found -- defaults apply)")
    for r in s:
        p(f"- `{r['name']}`.`{r['field']}` = `{r['v']}`")
    p("")

    # 2. Plan
    p("## 2. Planned writes")
    p(f"- `Stock Settings.stock_frozen_upto` -> `{SAFE_DATE}` (via direct SQL)")
    p(f"- `Accounts Settings.acc_frozen_upto` -> `{SAFE_DATE}` (via direct SQL)")
    p("")

    if not live:
        # Also show draft CS state in dry-run
        if frappe.db.exists("POS Closing Shift", draft):
            cs = frappe.db.get_value(
                "POS Closing Shift", draft,
                ["docstatus", "pos_opening_shift", "pos_profile"],
                as_dict=True,
            )
            p(f"## 3. Draft CS `{draft}` current state")
            p(f"- docstatus: {cs['docstatus']} (0=draft, 1=submitted)")
            p(f"- pos_opening_shift: `{cs['pos_opening_shift']}`")
            p(f"- pos_profile: `{cs['pos_profile']}`")
        else:
            p(f"## 3. Draft `{draft}` NOT FOUND.")
        p("")
        p("DRY-RUN -- re-run with LIVE=1 to apply.")
        _save(L)
        return

    # 3. LIVE writes
    p("## 3. Applying freeze-date fix via direct SQL")
    try:
        frappe.db.sql(
            "update `tabSingles` set value = %s "
            "where doctype = 'Stock Settings' and field = 'stock_frozen_upto'",
            (SAFE_DATE,),
        )
        # If no row exists, insert one
        n = frappe.db.sql(
            "select count(*) from `tabSingles` "
            "where doctype='Stock Settings' and field='stock_frozen_upto'"
        )[0][0]
        if n == 0:
            frappe.db.sql(
                "insert into `tabSingles` (doctype, field, value) values "
                "('Stock Settings', 'stock_frozen_upto', %s)",
                (SAFE_DATE,),
            )
        frappe.db.sql(
            "update `tabSingles` set value = %s "
            "where doctype = 'Accounts Settings' and field = 'acc_frozen_upto'",
            (SAFE_DATE,),
        )
        n = frappe.db.sql(
            "select count(*) from `tabSingles` "
            "where doctype='Accounts Settings' and field='acc_frozen_upto'"
        )[0][0]
        if n == 0:
            frappe.db.sql(
                "insert into `tabSingles` (doctype, field, value) values "
                "('Accounts Settings', 'acc_frozen_upto', %s)",
                (SAFE_DATE,),
            )
        frappe.db.commit()
        # Re-fetch single-cache
        frappe.clear_cache()
        p(f"- :white_check_mark: stock_frozen_upto = {SAFE_DATE}")
        p(f"- :white_check_mark: acc_frozen_upto = {SAFE_DATE}")
    except Exception as e:
        p(f"- :x: freeze-date write failed: {e}")
        _save(L)
        return
    p("")

    # 4. Verify via get_single_value
    new_stock = frappe.db.get_single_value("Stock Settings", "stock_frozen_upto")
    new_acc = frappe.db.get_single_value("Accounts Settings", "acc_frozen_upto")
    p("## 4. Verification")
    p(f"- get_single_value Stock = `{new_stock}` (type={type(new_stock).__name__})")
    p(f"- get_single_value Accounts = `{new_acc}` (type={type(new_acc).__name__})")
    p("")

    # 5. Submit the draft Closing Shift
    p(f"## 5. Submit draft `{draft}`")
    if not frappe.db.exists("POS Closing Shift", draft):
        p(f"- :x: `{draft}` not found. Did the insert get rolled back?")
        _save(L)
        return
    cs = frappe.get_doc("POS Closing Shift", draft)
    p(f"- docstatus before: {cs.docstatus}")
    if cs.docstatus == 1:
        p("- :information_source: already submitted -- nothing to do.")
    else:
        try:
            cs.submit()
            frappe.db.commit()
            p(f"- :white_check_mark: submitted -- docstatus now {cs.docstatus}")
        except Exception as e:
            p(f"- :x: submit failed: {type(e).__name__}: {e}")
            _save(L)
            return
    p("")

    # 6. Verify Opening Shift now closed
    p("## 6. Opening Shift status check")
    os_name = cs.pos_opening_shift
    os_status = frappe.db.get_value("POS Opening Shift", os_name, "status")
    p(f"- `{os_name}` status: **{os_status}**")
    _save(L)


def _save(L):
    out = "\n".join(L)
    Path("/tmp/p57_recover.log").write_text(out, encoding="utf-8")
    print(out)
    print()
    print("  Log: /tmp/p57_recover.log")


main()
