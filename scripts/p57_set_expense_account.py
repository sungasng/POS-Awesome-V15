"""
p57: Set Expense Account on sales Items / Item Groups so POS Awesome can
consolidate POS Invoices into a Sales Invoice without ValidationError.

Strategy:
  1. Find the company's Cost of Goods Sold-type account.
  2. List every Item that has been sold via POS but lacks an expense_account
     entry for this company.
  3. Optionally fall back to setting it at the Item Group level (broader scope).

Read-only by default. Set LIVE=1 to apply.

Parameters:
    LIVE          "1" to write. Default "0".
    EXPENSE_ACCT  Override account name. Default: auto-detect a COGS account.
    SCOPE         "item" (default) or "item_group". Where to write the default.
"""
from __future__ import annotations
from pathlib import Path
import os
import frappe

COMPANY = "SUNGAS COMPANY LIMITED"


def _detect_cogs_account() -> str | None:
    # Look for a Cost of Goods Sold leaf account in this company
    rows = frappe.db.sql("""
        select name, account_name from `tabAccount`
        where company = %s and disabled = 0 and is_group = 0
          and (account_type = 'Cost of Goods Sold'
               or account_name like '%%Cost of Goods Sold%%'
               or account_name like '%%COGS%%')
        order by name limit 5
    """, (COMPANY,), as_dict=True)
    return rows[0]["name"] if rows else None


def main():
    L = []
    p = L.append
    live = os.environ.get("LIVE", "0") == "1"
    scope = os.environ.get("SCOPE", "item").lower()
    override = os.environ.get("EXPENSE_ACCT")

    p("# p57 -- Set Expense Account on sales Items")
    p("")
    p(f"- Mode: {'LIVE' if live else 'DRY-RUN'}")
    p(f"- Scope: `{scope}` (item or item_group)")
    p("")

    acct = override or _detect_cogs_account()
    if not acct:
        p("**ABORT** -- could not detect a COGS account. Set EXPENSE_ACCT env var explicitly.")
        _save(L); return
    if not frappe.db.exists("Account", acct):
        p(f"**ABORT** -- account `{acct}` does not exist.")
        _save(L); return
    p(f"- Expense Account to use: **`{acct}`**")
    p("")

    # Show all COGS-shaped accounts so the user can pick a better one if needed
    candidates = frappe.db.sql("""
        select name, account_name, account_type from `tabAccount`
        where company = %s and disabled = 0 and is_group = 0
          and (account_type = 'Cost of Goods Sold'
               or account_name like '%%Cost of Goods Sold%%'
               or account_name like '%%COGS%%'
               or account_name like '%%Cost of Sales%%')
        order by name
    """, (COMPANY,), as_dict=True)
    p("## Candidate COGS accounts in CoA")
    for c in candidates:
        marker = "  <-- using this" if c["name"] == acct else ""
        p(f"- `{c['name']}` (type={c['account_type']}){marker}")
    p("")
    p("If you'd prefer a different account, re-run with `EXPENSE_ACCT='<name>'`.")
    p("")

    if scope == "item_group":
        # Set on every Item Group that doesn't already have one for this company
        groups = frappe.db.sql("""
            select name from `tabItem Group` where is_group = 0 order by name
        """, as_dict=True)
        p(f"## Item Group plan ({len(groups)} groups)")
        targets = []
        for g in groups:
            existing = frappe.db.get_value(
                "Item Default", {"parent": g["name"], "company": COMPANY}, "expense_account"
            )
            if not existing:
                targets.append(g["name"])
                p(f"- WILL SET on `{g['name']}` (currently empty)")
            elif existing != acct:
                p(f"- skip `{g['name']}` (already has `{existing}`)")
        p("")
        if not live:
            p("DRY-RUN -- no writes."); _save(L); return
        ok = 0
        for g in targets:
            try:
                doc = frappe.get_doc("Item Group", g)
                doc.append("item_group_defaults", {
                    "company": COMPANY,
                    "expense_account": acct,
                })
                doc.save(ignore_permissions=True)
                ok += 1
            except Exception as e:
                p(f"- :x: {g}: {e}")
        frappe.db.commit()
        p(f"**Updated**: {ok}")
        _save(L); return

    # Default: per-Item
    items = frappe.db.sql("""
        select name, item_name, item_group, is_stock_item, is_sales_item
        from `tabItem`
        where disabled = 0 and is_sales_item = 1
        order by name
    """, as_dict=True)
    p(f"## Item plan ({len(items)} sales items)")
    needs = []
    for it in items:
        existing = frappe.db.get_value(
            "Item Default", {"parent": it["name"], "company": COMPANY}, "expense_account"
        )
        if not existing:
            needs.append(it["name"])
    p(f"- Items missing Expense Account for {COMPANY}: **{len(needs)}**")
    for n in needs[:20]:
        p(f"  - {n}")
    if len(needs) > 20:
        p(f"  ... +{len(needs) - 20} more")
    p("")

    if not live:
        p("DRY-RUN -- re-run with `LIVE=1` to apply."); _save(L); return

    ok, failed = 0, []
    for name in needs:
        try:
            doc = frappe.get_doc("Item", name)
            # Either append a new row or update existing
            found = False
            for row in doc.item_defaults:
                if row.company == COMPANY:
                    row.expense_account = acct
                    found = True
                    break
            if not found:
                doc.append("item_defaults", {
                    "company": COMPANY,
                    "expense_account": acct,
                })
            doc.save(ignore_permissions=True)
            ok += 1
        except Exception as e:
            failed.append((name, str(e)))
    frappe.db.commit()
    p(f"**Updated**: {ok}    **Failed**: {len(failed)}")
    for n, e in failed[:10]:
        p(f"- :x: {n}: {e}")
    _save(L)


def _save(L):
    out = "\n".join(L)
    Path("/tmp/p57_expense_acct.log").write_text(out, encoding="utf-8")
    print(out)
    print()
    print(f"  Log: /tmp/p57_expense_acct.log")


main()
