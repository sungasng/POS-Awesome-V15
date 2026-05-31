"""
p57: Audit (and optionally repair) POS Profile Mode-of-Payment accounts.

Problem
=======
POS - Ikeja's "POS" mode of payment posts receipts to:
    1503 - POS Incoming - Pedro - SCL    (Pedro outlet account)
This is a copy-paste leftover from when profiles were cloned. It causes
all card sales at Ikeja to be booked to Pedro's books, distorting branch P&L.

Heuristic
=========
For each enabled POS Profile, infer the *expected* branch suffix from
the warehouse (e.g. "Ikeja - SCL" -> suffix "Ikeja"). For each Mode of
Payment row, extract the branch token from the account name (e.g.
"1503 - POS Incoming - Pedro - SCL" -> "Pedro"). If they differ, flag
as MISMATCH.

Repair is OPTIONAL and OFF by default. When LIVE=1 the script attempts
to find a matching account with the correct branch suffix and updates
the row. If no matching account exists, the row is left untouched and
listed for manual creation.

Parameters:
    LIVE     "1" to write. Default "0" (dry-run).
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime
import os
import re
import frappe


def _branch_from_warehouse(wh: str | None) -> str | None:
    """`Ikeja - SCL` -> 'Ikeja' ; `Pedro - SCL` -> 'Pedro'."""
    if not wh:
        return None
    # Strip the trailing company suffix
    parts = wh.rsplit(" - ", 1)
    return parts[0].strip() if len(parts) == 2 else wh.strip()


def _branch_from_account(acc: str | None) -> str | None:
    """`1503 - POS Incoming - Pedro - SCL` -> 'Pedro' (the second-to-last token)."""
    if not acc:
        return None
    # Account convention seen so far: "<code> - <name parts...> - <branch> - <company>"
    parts = [p.strip() for p in acc.split(" - ")]
    if len(parts) < 3:
        return None
    return parts[-2]


def _find_corrected_account(orig_acc: str, expected_branch: str) -> str | None:
    """
    Try to find an Account in the chart that matches `orig_acc` but with
    `expected_branch` in place of the wrong branch token.
    """
    parts = [p.strip() for p in orig_acc.split(" - ")]
    if len(parts) < 3:
        return None
    candidate_parts = parts[:]
    candidate_parts[-2] = expected_branch
    candidate = " - ".join(candidate_parts)
    if frappe.db.exists("Account", candidate):
        return candidate
    # Fallback: SQL LIKE search
    like = f"% - {expected_branch} - %"
    pattern = re.escape(parts[1]) if len(parts) > 1 else None
    if not pattern:
        return None
    rows = frappe.db.sql("""
        select name from `tabAccount`
        where account_name like %s and name like %s and disabled = 0
        limit 1
    """, (f"%{parts[1]}%", like), as_dict=True)
    return rows[0]["name"] if rows else None


def _detect_payment_child() -> tuple[str | None, str | None]:
    """Look at a real POS Profile's payments table to learn the child doctype + account field."""
    sample = frappe.db.get_value("POS Profile", {"disabled": 0}, "name")
    if not sample:
        return None, None
    pp = frappe.get_doc("POS Profile", sample)
    # POS Profile has a `payments` child table -- inspect first row's doctype + fields
    rows = getattr(pp, "payments", None)
    if not rows:
        return None, None
    first = rows[0]
    child_dt = first.doctype
    # find field that looks like an account link
    for fn in ("account", "default_account", "mop_account"):
        if hasattr(first, fn):
            return child_dt, fn
    # fall back: any DocField on the child whose options == "Account"
    df_rows = frappe.db.sql("""
        select fieldname from `tabDocField`
        where parent = %s and (options = 'Account' or fieldtype = 'Link' and options like '%%Account%%')
        limit 1
    """, (child_dt,), as_dict=True)
    if df_rows:
        return child_dt, df_rows[0]["fieldname"]
    return child_dt, None


def main():
    L = []
    p = L.append
    live = os.environ.get("LIVE", "0") == "1"
    p("# p57 -- POS Profile Mode-of-Payment account audit"); p("")
    p(f"- Mode: {'LIVE' if live else 'DRY-RUN'}")
    p(f"- Run by: `{frappe.session.user}` at `{datetime.utcnow().isoformat()}Z`")
    p("")

    profiles = frappe.db.sql("""
        select name, warehouse, cost_center
        from `tabPOS Profile` where disabled = 0
        order by name
    """, as_dict=True)
    p(f"- Active POS Profiles: **{len(profiles)}**")

    # Determine the actual child doctype + account field POS Awesome uses on this site
    child_dt, acct_field = _detect_payment_child()
    if not child_dt:
        p("**ABORT** -- could not detect POS Profile payment child table.")
        _save(L); return
    p(f"- Payment rows live in child doctype `{child_dt}`, account column `{acct_field}`")
    p("")

    findings: list[dict] = []
    for pp in profiles:
        expected = _branch_from_warehouse(pp["warehouse"])
        pay_rows = frappe.db.sql(f"""
            select name, parent, mode_of_payment, `{acct_field}` as account
            from `tab{child_dt}`
            where parenttype = 'POS Profile' and parent = %s
            order by mode_of_payment
        """, (pp["name"],), as_dict=True)
        for r in pay_rows:
            actual = _branch_from_account(r["account"])
            mismatch = bool(expected and actual and expected.lower() != actual.lower())
            findings.append({
                "profile": pp["name"],
                "warehouse": pp["warehouse"],
                "expected_branch": expected,
                "mode": r["mode_of_payment"],
                "account": r["account"],
                "actual_branch": actual,
                "mismatch": mismatch,
                "row_name": r["name"],
                "child_dt": child_dt,
                "acct_field": acct_field,
            })

    p("## Findings")
    p("| Profile | Mode | Account | Expected branch | Actual branch | Match |")
    p("|---------|------|---------|-----------------|---------------|-------|")
    for f in findings:
        marker = ":x: MISMATCH" if f["mismatch"] else ":white_check_mark: OK"
        p(f"| {f['profile']} | {f['mode']} | {f['account']} | {f['expected_branch']} | "
          f"{f['actual_branch']} | {marker} |")
    p("")

    mismatches = [f for f in findings if f["mismatch"]]
    p(f"**Mismatches found**: {len(mismatches)}")
    p("")

    if not mismatches:
        p("No remediation required.")
        _save(L); return

    # Compute proposed corrections
    p("## Proposed corrections")
    repairable, manual = [], []
    for f in mismatches:
        suggested = _find_corrected_account(f["account"], f["expected_branch"])
        if suggested:
            repairable.append({**f, "new_account": suggested})
        else:
            manual.append(f)

    if repairable:
        p("### Repairable -- a matching account exists with the correct branch")
        p("| Profile | Mode | From | To |")
        p("|---------|------|------|----|")
        for f in repairable:
            p(f"| {f['profile']} | {f['mode']} | {f['account']} | **{f['new_account']}** |")
        p("")
    if manual:
        p("### Manual review -- no matching account exists with the correct branch")
        p("These need a new GL account created (Chart of Accounts) before repair.")
        p("| Profile | Mode | Current account | Expected branch |")
        p("|---------|------|-----------------|-----------------|")
        for f in manual:
            p(f"| {f['profile']} | {f['mode']} | {f['account']} | {f['expected_branch']} |")
        p("")

    if not live:
        p("**DRY-RUN** -- re-run with `LIVE=1` to apply the repairable corrections.")
        _save(L); return

    # ---- LIVE ----
    p("## Applying repairable corrections")
    ok, failed = 0, []
    for f in repairable:
        try:
            frappe.db.set_value(f["child_dt"], f["row_name"],
                                f["acct_field"], f["new_account"])
            ok += 1
            p(f"- :white_check_mark: {f['profile']} / {f['mode']} -> {f['new_account']}")
        except Exception as e:
            failed.append((f["profile"], str(e)))
            p(f"- :x: {f['profile']} / {f['mode']}: {e}")
    frappe.db.commit()
    p("")
    p(f"**Applied**: {ok}    **Failed**: {len(failed)}")
    p("")
    p("## Important next steps for HOD Finance")
    p("1. **Forward-looking**: Future Ikeja card receipts will post to the correct GL.")
    p("2. **Backward-looking (historical mis-posting)**: A separate Journal Entry is")
    p("   required to move past card receipts from the wrong branch GL to the correct one.")
    p("   This requires HOD Finance review. Calculate impact by running:")
    p("     `bench --site sungasmis.v.frappe.cloud console` and checking GL Entry for")
    p("     the misallocated accounts since each profile's first card receipt.")
    p("3. Re-run this script with LIVE=0 to confirm 0 mismatches remain.")
    _save(L)


def _save(L):
    out = "\n".join(L)
    Path("/tmp/p57_pp_audit.log").write_text(out, encoding="utf-8")
    print(out)
    print()
    print(f"  Log: /tmp/p57_pp_audit.log")


main()
