"""
p57: Diagnose any currently OPEN POS Opening Shift -- surfaces the real reason
POS Awesome's UI swallowed the close attempt.

Strategy:
  1. List all OPEN shifts (status='Open' OR docstatus=1 but never closed).
  2. For each: linked invoices, computed MoP totals, recent Error Log entries
     mentioning the shift / cashier, and a DRY-RUN attempt to build a Closing
     Shift in-memory -- if that fails, the exception bubbles up here cleanly.
  3. Validates referenced MoPs + accounts: enabled, not disabled, account
     exists, has correct company.
  4. Checks that the period the shift sits in is NOT account/stock frozen.

Read-only. No writes.
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime, timedelta
import traceback
import frappe
from frappe.utils import getdate, get_datetime

COMPANY = "SUNGAS COMPANY LIMITED"


def main():
    L = []
    p = L.append
    p("# p57: Diagnose all currently OPEN POS Opening Shifts")
    p("")
    p(f"- Run at: `{datetime.utcnow().isoformat()}Z`")
    p(f"- Run by: `{frappe.session.user}`")
    p("")

    # 1) Discover open shifts (all users, all profiles)
    opens = frappe.get_all(
        "POS Opening Shift",
        filters={"status": "Open", "docstatus": 1},
        fields=["name", "pos_profile", "user", "period_start_date", "modified"],
        order_by="period_start_date desc",
    )
    p(f"## 1. Currently OPEN POS Opening Shifts: **{len(opens)}**")
    if not opens:
        p("- (no open shifts) -- nothing to diagnose.")
        _save(L)
        return
    p("| Shift | Profile | Cashier | Started | Modified |")
    p("|-------|---------|---------|---------|----------|")
    for o in opens:
        p(f"| `{o['name']}` | {o['pos_profile']} | {o['user']} | "
          f"{o['period_start_date']} | {o['modified']} |")
    p("")

    # Period-lock context
    stock_freeze = frappe.db.get_single_value("Stock Settings", "stock_frozen_upto") or ""
    acc_freeze = frappe.db.get_single_value("Accounts Settings", "acc_frozen_upto") or ""
    p(f"- stock_frozen_upto: `{stock_freeze}`")
    p(f"- acc_frozen_upto:   `{acc_freeze}`")
    p("")

    # 2) Per-shift deep dive
    for o in opens:
        p(f"## 2.{opens.index(o)+1}. Deep dive: `{o['name']}`")
        _dive(p, o, stock_freeze, acc_freeze)
        p("")

    # 3) Recent Error Log entries (since last 24h) mentioning POS or Peace
    p("## 3. Error Log (last 24h) mentioning POS / Closing Shift / cashier emails")
    cutoff = (datetime.utcnow() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
    rows = frappe.db.sql("""
        select name, creation, method, left(error, 600) as snippet
        from `tabError Log`
        where creation >= %s
          and (error like '%%POS Closing Shift%%'
               or error like '%%POS Opening Shift%%'
               or error like '%%POSA-OS%%'
               or error like '%%pos_invoice%%'
               or error like '%%POS Awesome%%'
               or method like '%%posawesome%%')
        order by creation desc
        limit 25
    """, (cutoff,), as_dict=True)
    if not rows:
        p("- (no relevant POS errors in last 24h)")
    else:
        for r in rows:
            snippet = (r["snippet"] or "").replace("\n", " | ")
            p(f"### `{r['name']}` -- {r['creation']} -- method=`{r['method']}`")
            p("```")
            p(snippet[:600])
            p("```")
    p("")
    p("---")
    p("If section 2 surfaced a specific exception, that's the actual bug to fix.")
    p("If sections 2 and 3 are clean and shift still won't close from UI, the issue")
    p("is a client-side JS handler that's silently catching the response.")
    _save(L)


def _dive(p, o: dict, stock_freeze, acc_freeze):
    name = o["name"]
    # Linked invoices
    invs = frappe.get_all(
        "POS Invoice",
        filters={"posa_pos_opening_shift": name, "docstatus": 1},
        fields=["name", "posting_date", "customer", "grand_total", "status"],
        order_by="posting_date, creation",
    )
    p(f"- linked POS Invoices: **{len(invs)}**, sum grand_total = "
      f"NGN {sum(i['grand_total'] for i in invs):,.2f}")
    for i in invs:
        p(f"  - {i['name']} | {i['posting_date']} | {i['customer']} | "
          f"NGN {i['grand_total']:,.2f} | status={i['status']}")
    p("")

    # Check freeze guards: if any invoice's posting_date <= stock_freeze, close
    # will fail because consolidation creates new Sales Invoice posting back-dated.
    p("### Freeze-date guard")
    if invs:
        earliest = min(getdate(i["posting_date"]) for i in invs)
        latest = max(getdate(i["posting_date"]) for i in invs)
        p(f"- invoice posting_date range: {earliest} .. {latest}")
        if stock_freeze and stock_freeze != "0001-01-01":
            sfd = getdate(stock_freeze)
            if earliest <= sfd:
                p(f"- :rotating_light: **{earliest} is on/before stock_frozen_upto `{sfd}`** -- "
                  f"close WILL be rejected at consolidation. This is the most likely cause.")
            else:
                p(f"- :white_check_mark: earliest invoice {earliest} > stock_frozen_upto {sfd}")
        if acc_freeze and acc_freeze != "0001-01-01":
            afd = getdate(acc_freeze)
            if earliest <= afd:
                p(f"- :rotating_light: **{earliest} is on/before acc_frozen_upto `{afd}`** -- "
                  f"close WILL be rejected at GL posting.")
            else:
                p(f"- :white_check_mark: earliest invoice {earliest} > acc_frozen_upto {afd}")
    p("")

    # Mode of Payment + Account validation
    p("### Mode of Payment + Account validation (from linked invoices)")
    seen_mops = set()
    for i in invs:
        try:
            inv_doc = frappe.get_doc("POS Invoice", i["name"])
            for pmt in inv_doc.payments:
                if pmt.mode_of_payment in seen_mops:
                    continue
                seen_mops.add(pmt.mode_of_payment)
                mop_doc = frappe.get_doc("Mode of Payment", pmt.mode_of_payment)
                acc_row = next((a for a in mop_doc.accounts if a.company == COMPANY), None)
                p(f"- `{pmt.mode_of_payment}`: type={mop_doc.type}, enabled={mop_doc.enabled}, "
                  f"company_default_account=`{acc_row.default_account if acc_row else '(none)'}`")
                if acc_row and acc_row.default_account:
                    acc = frappe.db.get_value(
                        "Account", acc_row.default_account,
                        ["disabled", "company", "account_type", "is_group"],
                        as_dict=True,
                    )
                    if not acc:
                        p(f"  :x: account `{acc_row.default_account}` not found")
                    elif acc.disabled:
                        p(f"  :x: account `{acc_row.default_account}` is DISABLED")
                    elif acc.is_group:
                        p(f"  :x: account `{acc_row.default_account}` is a GROUP (must be leaf)")
                    elif acc.company != COMPANY:
                        p(f"  :x: account belongs to company `{acc.company}` not `{COMPANY}`")
        except Exception as e:
            p(f"- :x: error validating invoice `{i['name']}`: {e}")
    p("")

    # Item Defaults: every item on every linked invoice must have expense_account
    # AND income_account for the company.
    p("### Item Defaults check on items used in this shift")
    item_codes = set()
    for i in invs:
        rows = frappe.db.sql("""
            select distinct item_code from `tabPOS Invoice Item`
            where parent = %s
        """, (i["name"],), as_dict=True)
        for r in rows:
            item_codes.add(r["item_code"])
    bad_items = []
    for ic in sorted(item_codes):
        ea = frappe.db.get_value(
            "Item Default", {"parent": ic, "company": COMPANY},
            "expense_account",
        )
        ia = frappe.db.get_value(
            "Item Default", {"parent": ic, "company": COMPANY},
            "income_account",
        )
        if not ea or not ia:
            bad_items.append((ic, ea, ia))
    if not bad_items:
        p(f"- :white_check_mark: all {len(item_codes)} item(s) have both expense_account "
          "and income_account set.")
    else:
        p(f"- :x: {len(bad_items)} item(s) missing defaults:")
        for ic, ea, ia in bad_items:
            p(f"  - `{ic}`: expense=`{ea or '(MISSING)'}` income=`{ia or '(MISSING)'}`")
    p("")

    # DRY-RUN: simulate building a POS Closing Shift in-memory and validate it.
    p("### Dry-run: simulate POS Closing Shift validation")
    try:
        os_doc = frappe.get_doc("POS Opening Shift", name)
        cs = frappe.new_doc("POS Closing Shift")
        cs.pos_opening_shift = name
        cs.pos_profile = os_doc.pos_profile
        cs.user = os_doc.user
        cs.company = os_doc.company
        cs.period_start_date = os_doc.period_start_date
        cs.period_end_date = frappe.utils.now_datetime()
        cs.posting_date = frappe.utils.nowdate()
        # Aggregate MoP totals from invoices
        mop_totals = {}
        for i in invs:
            for pmt in frappe.get_doc("POS Invoice", i["name"]).payments:
                mop_totals[pmt.mode_of_payment] = mop_totals.get(
                    pmt.mode_of_payment, 0
                ) + (pmt.amount or 0)
        for mop, amt in mop_totals.items():
            cs.append("payment_reconciliation", {
                "mode_of_payment": mop,
                "expected_amount": amt,
                "closing_amount": amt,
                "difference": 0,
            })
        # Attach invoice refs
        for i in invs:
            cs.append("pos_transactions", {"pos_invoice": i["name"]})
        cs.grand_total = sum(i["grand_total"] for i in invs)
        cs.net_total = cs.grand_total
        cs.total_quantity = 0
        # Validate without inserting
        cs.validate()
        p("- :white_check_mark: `validate()` passed cleanly. "
          "If UI still fails, suspect a client-side handler that swallows the response.")
    except Exception as e:
        p(f"- :x: validate() raised: **{type(e).__name__}: {e}**")
        p("```")
        for line in traceback.format_exc().splitlines()[-20:]:
            p(line)
        p("```")


def _save(L):
    out = "\n".join(L)
    Path("/tmp/p57_diagnose_open.log").write_text(out, encoding="utf-8")
    print(out)
    print()
    print("  Log: /tmp/p57_diagnose_open.log")


main()
