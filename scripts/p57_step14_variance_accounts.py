"""
p57 / Step 14 -- Cash Variance accounts + backfill today's variance JEs.

Locks in the 4-account architecture for cash-variance accounting:
  1602  Cash Suspense - Cashier Recovery - SCL    (Asset / Receivable)
  2702  Cash Overage Suspense - SCL                (Liability)
  8203  Cash Shortage - Written Off - SCL          (Expense)
  7205  Cash Overage - Time-Barred Income - SCL    (Income)

WAVE=1  PLAN          (read-only)
                      - Enumerates Asset/Liability/Expense/Income parents
                      - Proposes which existing parent to use for each new account
                      - Summarises today's POS Closing Shift variances + planned backfill JEs
WAVE=2  ACCOUNTS      Creates the 4 new accounts under user-confirmed parents
                      (parents passed via env vars; defaults set from Wave-1 discovery)
WAVE=3  BACKFILL_JE   Posts a Journal Entry per Closing Shift submitted today with
                      non-zero variance. Shortage -> Dr 1602/Cr Cash Sales; Overage ->
                      Dr Cash Sales/Cr 2702. Party=Employee for shortage row.
WAVE=4  REWIRE_PROF   (optional, not used yet) Set POS Profile write_off_account
                      to 1602 to allow ERPNext native posting when it eventually
                      adds support. Right now the POS Awesome on_submit doesn't
                      auto-post variance; the Phase-2 hook does it instead.

Parameters:
    WAVE                "1" | "2" | "3" | "4"
    LIVE                "1" to write. Default "0".
    PARENT_RECEIVABLE   Parent account for 1602. Default discovered.
    PARENT_LIABILITY    Parent account for 2702. Default discovered.
    PARENT_EXPENSE      Parent account for 8203. Default discovered.
    PARENT_INCOME       Parent account for 7205. Default = "7200 - Other Income - SCL"
"""
from __future__ import annotations
from pathlib import Path
from datetime import date, datetime
import os
import frappe

COMPANY = "SUNGAS COMPANY LIMITED"
COMPANY_ABBR = "SCL"

BUCKETS = [
    {
        "code": "1602",
        "name": "Cash Suspense - Cashier Recovery",
        "full": f"1602 - Cash Suspense - Cashier Recovery - {COMPANY_ABBR}",
        "root_type": "Asset",
        "account_type": "Receivable",
        "env_parent": "PARENT_RECEIVABLE",
    },
    {
        "code": "2702",
        "name": "Cash Overage Suspense",
        "full": f"2702 - Cash Overage Suspense - {COMPANY_ABBR}",
        "root_type": "Liability",
        "account_type": "Payable",
        "env_parent": "PARENT_LIABILITY",
    },
    {
        "code": "8203",
        "name": "Cash Shortage - Written Off",
        "full": f"8203 - Cash Shortage - Written Off - {COMPANY_ABBR}",
        "root_type": "Expense",
        "account_type": "Expense Account",
        "env_parent": "PARENT_EXPENSE",
    },
    {
        "code": "7205",
        "name": "Cash Overage - Time-Barred Income",
        "full": f"7205 - Cash Overage - Time-Barred Income - {COMPANY_ABBR}",
        "root_type": "Income",
        "account_type": "Income Account",
        "env_parent": "PARENT_INCOME",
    },
]


def _save(L, fname="p57_step14"):
    out = "\n".join(L)
    Path(f"/tmp/{fname}.log").write_text(out, encoding="utf-8")
    print(out)
    print()
    print(f"  Log: /tmp/{fname}.log")


def _list_groups(root_type: str) -> list:
    return frappe.db.sql("""
        select name, account_number, lft, rgt
        from `tabAccount`
        where company = %s and is_group = 1 and root_type = %s
        order by lft
    """, (COMPANY, root_type), as_dict=True)


def _guess_parent(root_type: str, code_prefix: str) -> str | None:
    """Find the most likely parent group based on code-number proximity."""
    groups = _list_groups(root_type)
    if not groups:
        return None
    # Prefer a group whose code range contains the new code
    code = int(code_prefix)
    for g in groups:
        # account_number sometimes "1600-1699"
        an = (g.get("account_number") or "")
        if "-" in an:
            try:
                lo, hi = [int(x.strip()) for x in an.split("-")]
                if lo <= code <= hi:
                    return g["name"]
            except Exception:
                pass
    # Fallback: first group of that root_type
    return groups[0]["name"] if groups else None


def wave1_plan(L):
    p = L.append
    p("# p57 / Step 14 / WAVE 1 -- Plan (read-only)")
    p("")
    p(f"- Company: `{COMPANY}`")
    p("")

    p("## 1. CoA parent group accounts by root type")
    for rt in ["Asset", "Liability", "Expense", "Income"]:
        groups = _list_groups(rt)
        p(f"### {rt} group accounts ({len(groups)})")
        for g in groups:
            p(f"- `{g['name']}` (code={g.get('account_number') or '-'})")
        p("")

    p("## 2. Proposed accounts to create (WAVE 2)")
    p("| Code | Account | Root | Type | Proposed Parent | Override env var |")
    p("|------|---------|------|------|-----------------|------------------|")
    for b in BUCKETS:
        guessed = _guess_parent(b["root_type"], b["code"])
        env_value = os.environ.get(b["env_parent"])
        parent = env_value or guessed or "(NONE FOUND)"
        if frappe.db.exists("Account", b["full"]):
            status = ":white_check_mark: EXISTS"
        elif env_value:
            status = ":sparkles: WILL CREATE (env override)"
        elif guessed:
            status = ":sparkles: WILL CREATE (auto-pick)"
        else:
            status = ":x: NO PARENT FOUND"
        p(f"| {b['code']} | {b['name']} | {b['root_type']} | {b['account_type']} | "
          f"`{parent}` | `{b['env_parent']}` | {status} |")
    p("")
    p("To override a parent: `export PARENT_RECEIVABLE='1600 - Current Receivables - SCL'` etc.")
    p("")

    # Today's variance summary
    today = date.today()
    p(f"## 3. Today's POS Closing Shift variances ({today})")
    rows = frappe.db.sql("""
        select cs.name, cs.pos_profile, cs.user, cs.modified_by,
               sum(d.expected_amount) as expected,
               sum(d.closing_amount) as closing,
               (sum(d.closing_amount) - sum(d.expected_amount)) as variance
        from `tabPOS Closing Shift` cs
        join `tabPOS Closing Shift Detail` d on d.parent = cs.name
        where date(cs.period_end_date) = %s and cs.docstatus = 1
        group by cs.name
        having abs(variance) > 0.01
        order by cs.modified desc
    """, (today,), as_dict=True)
    if not rows:
        p("- (no closing shifts with non-zero variance today)")
    else:
        p("| Closing Shift | Outlet | Cashier | Expected | Closing | Variance |")
        p("|---------------|--------|---------|---------:|--------:|---------:|")
        total = 0
        for r in rows:
            total += r["variance"] or 0
            flag = ":rotating_light:" if abs(r["variance"]) >= 100000 else (
                ":warning:" if abs(r["variance"]) >= 10000 else "")
            p(f"| `{r['name']}` | {r['pos_profile']} | {r['user']} | "
              f"{r['expected']:,.2f} | {r['closing']:,.2f} | "
              f"{r['variance']:+,.2f} {flag} |")
        p(f"\n**Total variance: NGN {total:+,.2f}**")
    p("")

    # Cash Sales account inference
    p("## 4. Backfill JE plan (WAVE 3)")
    if rows:
        p("Per Closing Shift with non-zero variance, post 1 Journal Entry:")
        p("- Shortage (variance < 0): Dr `1602 Cash Suspense - Cashier Recovery` "
          "(party=Employee:<cashier>) / Cr `Cash Sales - <Outlet>` for abs(variance)")
        p("- Overage (variance > 0): Dr `Cash Sales - <Outlet>` / "
          "Cr `2702 Cash Overage Suspense` for abs(variance)")
        p("")
        p(f"Total backfill JEs to create: **{len(rows)}**")
    else:
        p("- nothing to backfill.")
    p("")
    p("---")
    p("Next:")
    p("1. Review proposed parents above. Override via PARENT_* env vars if needed.")
    p("2. `WAVE=2 LIVE=1` to create the 4 GL accounts.")
    p("3. `WAVE=3 LIVE=1` to post backfill JEs.")


def wave2_accounts(L, live: bool):
    p = L.append
    p("# p57 / Step 14 / WAVE 2 -- Create variance accounts")
    p("")
    p(f"- Mode: {'LIVE' if live else 'DRY-RUN'}")
    p("")
    created, skipped, failed = 0, 0, []
    for b in BUCKETS:
        if frappe.db.exists("Account", b["full"]):
            skipped += 1
            p(f"- skip `{b['full']}` (already exists)")
            continue
        env_value = os.environ.get(b["env_parent"])
        parent = env_value or _guess_parent(b["root_type"], b["code"])
        if not parent or not frappe.db.exists("Account", parent):
            failed.append((b["full"], f"no parent found (env={b['env_parent']})"))
            p(f"- :x: `{b['full']}`: no parent found (set env `{b['env_parent']}`)")
            continue
        if not live:
            p(f"- WOULD CREATE `{b['full']}` under `{parent}` "
              f"(root={b['root_type']}, type={b['account_type']})")
            continue
        try:
            parent_doc = frappe.get_doc("Account", parent)
            doc = frappe.get_doc({
                "doctype": "Account",
                "account_name": b["name"],
                "account_number": b["code"],
                "parent_account": parent,
                "company": COMPANY,
                "account_type": b["account_type"],
                "root_type": b["root_type"],
                "report_type": (
                    "Profit and Loss"
                    if b["root_type"] in ("Income", "Expense") else "Balance Sheet"
                ),
                "is_group": 0,
                "account_currency": parent_doc.account_currency or "NGN",
            })
            doc.insert(ignore_permissions=True)
            created += 1
            p(f"- :white_check_mark: created `{doc.name}`")
        except Exception as e:
            failed.append((b["full"], str(e)))
            p(f"- :x: `{b['full']}`: {e}")
    if live:
        frappe.db.commit()
    p("")
    p(f"**Created**: {created}    **Skipped**: {skipped}    **Failed**: {len(failed)}")


def _cash_sales_account_for_profile(profile_name: str) -> str | None:
    """Look up the Mode of Payment named 'Cash - SCL - <Outlet>' for this profile
    and return its company default_account."""
    prof = frappe.db.get_value("POS Profile", profile_name, "warehouse")
    if not prof:
        return None
    outlet = prof.rsplit(" - ", 1)[0].strip() if " - " in prof else prof.strip()
    # Try direct MoP lookup first
    mop_name = f"Cash - {COMPANY_ABBR} - {outlet}"
    if frappe.db.exists("Mode of Payment", mop_name):
        acc = frappe.db.sql("""
            select default_account from `tabMode of Payment Account`
            where parent = %s and company = %s
        """, (mop_name, COMPANY), as_dict=True)
        if acc:
            return acc[0]["default_account"]
    # Fallback: search any cash account for this outlet
    rows = frappe.db.sql("""
        select name from `tabAccount`
        where company = %s and disabled = 0 and is_group = 0
          and name like %s
        limit 1
    """, (COMPANY, f"%Cash Sales - {outlet}%"), as_dict=True)
    return rows[0]["name"] if rows else None


def _employee_for_user(user_email: str) -> str | None:
    return frappe.db.get_value("Employee", {"user_id": user_email}, "name")


def wave3_backfill(L, live: bool):
    p = L.append
    p("# p57 / Step 14 / WAVE 3 -- Backfill variance Journal Entries")
    p("")
    p(f"- Mode: {'LIVE' if live else 'DRY-RUN'}")
    p("")

    # Pre-check accounts exist
    shortage_acct = next(b["full"] for b in BUCKETS if b["code"] == "1602")
    overage_acct = next(b["full"] for b in BUCKETS if b["code"] == "2702")
    if not frappe.db.exists("Account", shortage_acct):
        p(f"**ABORT** -- `{shortage_acct}` does not exist (run WAVE 2 first)")
        return
    if not frappe.db.exists("Account", overage_acct):
        p(f"**ABORT** -- `{overage_acct}` does not exist (run WAVE 2 first)")
        return

    today = date.today()
    rows = frappe.db.sql("""
        select cs.name, cs.pos_profile, cs.user, cs.period_end_date,
               sum(d.expected_amount) as expected,
               sum(d.closing_amount) as closing,
               (sum(d.closing_amount) - sum(d.expected_amount)) as variance
        from `tabPOS Closing Shift` cs
        join `tabPOS Closing Shift Detail` d on d.parent = cs.name
        where date(cs.period_end_date) = %s and cs.docstatus = 1
        group by cs.name
        having abs(variance) > 0.01
        order by cs.modified
    """, (today,), as_dict=True)

    if not rows:
        p("- (no variances to backfill today)")
        return

    p(f"- Shifts with variance to backfill: **{len(rows)}**")
    created, skipped, failed = 0, 0, []
    for r in rows:
        # Idempotency: skip if a JE already references this closing shift in remarks
        existing = frappe.db.sql("""
            select name from `tabJournal Entry`
            where company = %s and docstatus = 1
              and (user_remark like %s or title like %s)
        """, (COMPANY, f"%{r['name']}%", f"%{r['name']}%"))
        if existing:
            skipped += 1
            p(f"- skip `{r['name']}` (JE `{existing[0][0]}` already exists)")
            continue

        cash_acct = _cash_sales_account_for_profile(r["pos_profile"])
        if not cash_acct:
            failed.append((r["name"], "no Cash Sales account resolved"))
            p(f"- :x: `{r['name']}`: no Cash Sales account resolved for "
              f"profile `{r['pos_profile']}`")
            continue
        variance = float(r["variance"])
        abs_var = abs(variance)
        emp = _employee_for_user(r["user"])

        if variance < 0:  # shortage
            short_row = {
                "account": shortage_acct,
                "debit_in_account_currency": abs_var,
                "credit_in_account_currency": 0,
            }
            if emp:
                short_row["party_type"] = "Employee"
                short_row["party"] = emp
            entries = [
                short_row,
                {
                    "account": cash_acct,
                    "debit_in_account_currency": 0,
                    "credit_in_account_currency": abs_var,
                },
            ]
            kind = "Shortage"
        else:  # overage
            entries = [
                {
                    "account": cash_acct,
                    "debit_in_account_currency": abs_var,
                    "credit_in_account_currency": 0,
                },
                {
                    "account": overage_acct,
                    "debit_in_account_currency": 0,
                    "credit_in_account_currency": abs_var,
                },
            ]
            kind = "Overage"

        remark = (
            f"Cash {kind} backfill for POS Closing Shift {r['name']} "
            f"({r['pos_profile']}, cashier={r['user']}). "
            f"Expected NGN {r['expected']:,.2f}, "
            f"Closing NGN {r['closing']:,.2f}, "
            f"Variance NGN {variance:+,.2f}."
        )
        if not live:
            p(f"- WOULD POST {kind} JE for `{r['name']}` (NGN {abs_var:,.2f})")
            for e in entries:
                p(f"    {e['account']} Dr {e.get('debit_in_account_currency', 0):,.2f} "
                  f"Cr {e.get('credit_in_account_currency', 0):,.2f}")
            continue

        try:
            je = frappe.get_doc({
                "doctype": "Journal Entry",
                "voucher_type": "Journal Entry",
                "company": COMPANY,
                "posting_date": frappe.utils.nowdate(),
                "title": f"Cash {kind} - {r['name']}",
                "user_remark": remark,
                "accounts": entries,
            })
            je.insert(ignore_permissions=True)
            je.submit()
            frappe.db.commit()
            created += 1
            p(f"- :white_check_mark: posted `{je.name}` for `{r['name']}` "
              f"({kind}, NGN {abs_var:,.2f})")
        except Exception as e:
            failed.append((r["name"], str(e)))
            p(f"- :x: `{r['name']}`: {e}")

    p("")
    p(f"**Created**: {created}    **Skipped**: {skipped}    **Failed**: {len(failed)}")
    for n, e in failed[:10]:
        p(f"- :x: {n}: {e}")


def wave4_rewire(L, live: bool):
    p = L.append
    p("# p57 / Step 14 / WAVE 4 -- (informational) POS Profile write_off audit")
    p("")
    profs = frappe.get_all(
        "POS Profile",
        filters={"company": COMPANY, "disabled": 0},
        fields=["name", "write_off_account"],
        order_by="name",
    )
    p(f"- POS Profiles: {len(profs)}")
    p("| Profile | Current write_off_account |")
    p("|---------|---------------------------|")
    for p_ in profs:
        p(f"| `{p_['name']}` | `{p_['write_off_account'] or '(unset)'}` |")
    p("")
    p("Note: ERPNext POS Awesome does not auto-post variance to write_off_account")
    p("on Closing Shift submit. Variance JEs are posted by the WAVE 3 backfill")
    p("(historical) and by the on_submit hook (Phase 2, not yet installed).")


def main():
    L = []
    wave = os.environ.get("WAVE", "").strip()
    live = os.environ.get("LIVE", "0") == "1"
    if wave == "1":
        wave1_plan(L)
    elif wave == "2":
        wave2_accounts(L, live)
    elif wave == "3":
        wave3_backfill(L, live)
    elif wave == "4":
        wave4_rewire(L, live)
    else:
        L.append("ERROR: set WAVE=1|2|3|4 (and LIVE=1 for write waves).")
    _save(L, fname=f"p57_step14_wave{wave or 'X'}")


main()
