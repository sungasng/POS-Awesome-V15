"""
p57 / Step 10 -- Per-outlet Mode of Payment migration.

Single composite script. Each "wave" is independently runnable and the
overall flow is:
  WAVE=1  Plan          (read-only -- safe always)
  WAVE=2  Create MOPs   (creates 63 records; idempotent)
  WAVE=3  Rewire POS Profiles (sets each profile's payment children to outlet-specific MOPs)
  WAVE=4  Disable generics (Cash, POS, Transfer, Bank Draft, Cheque, Credit Card, Wire Transfer)
  WAVE=5  Journal Entry draft to correct historic Ikeja POS misposting (NGN 228,000)

Conventions agreed with user:
  - Mode of Payment naming: `<Mode> - SCL - <Outlet>` (Cash - SCL - Ikeja, POS - SCL - Ikeja, Transfer - SCL - Ikeja)
  - Outlet name derived from POS Profile warehouse (warehouse = "Ikeja - SCL" -> outlet = "Ikeja")
  - GL account naming patterns:
        Cash     -> "1101 - Cash Sales - {outlet} - SCL"
        POS      -> "1503 - POS Incoming - {outlet} - SCL"
        Transfer -> "1511 - Incoming Transfer - {outlet} - SCL"

Parameters:
    WAVE   "1" | "2" | "3" | "4" | "5". Required.
    LIVE   "1" to write. Default "0" (dry-run). Ignored for WAVE=1.
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime, date
import os
import frappe

COMPANY = "SUNGAS COMPANY LIMITED"
COMPANY_ABBR = "SCL"
MODES = ["Cash", "POS", "Transfer"]
MODE_TYPE = {"Cash": "Cash", "POS": "Bank", "Transfer": "Bank"}
# Account-name keyword per mode -- looked up by SQL LIKE since codes vary
ACC_KEYWORD = {
    "Cash": "Cash Sales",
    "POS": "POS Incoming",
    "Transfer": "Incoming Transfer",
}
# Outlet name variants used in GL Account naming vs POS Profile warehouse
OUTLET_ALIAS = {
    "Iju-Otta": ["Iju-Otta", "Iju-Ota"],
    "Ebutte": ["Ebutte", "Ebute"],
    "Osi-Otta": ["Osi-Otta", "Osi-Ota"],
}
DISABLE_MOPS = ["Cash", "POS", "Transfer", "Bank Draft", "Cheque", "Credit Card", "Wire Transfer"]


def _resolve_account(mode: str, outlet: str) -> str | None:
    """Find the existing GL account for (mode, outlet) using SQL LIKE
    on the keyword + any spelling variant of the outlet name."""
    kw = ACC_KEYWORD[mode]
    variants = OUTLET_ALIAS.get(outlet, [outlet])
    for v in variants:
        pattern = f"% - {kw} - {v} - {COMPANY_ABBR}"
        rows = frappe.db.sql("""
            select name from `tabAccount`
            where company = %s and disabled = 0 and is_group = 0
              and name like %s
            limit 1
        """, (COMPANY, pattern), as_dict=True)
        if rows:
            return rows[0]["name"]
    return None


# ---------------- helpers ----------------

def _outlet_from_warehouse(wh: str | None) -> str | None:
    if not wh:
        return None
    return wh.rsplit(" - ", 1)[0].strip() if " - " in wh else wh.strip()


def _expected_account(mode: str, outlet: str) -> str | None:
    """Returns the resolved account name (existing in CoA), or None if not found."""
    return _resolve_account(mode, outlet)


def _mop_name(mode: str, outlet: str) -> str:
    return f"{mode} - {COMPANY_ABBR} - {outlet}"


def _save(L, fname="p57_step10.log"):
    out = "\n".join(L)
    Path(f"/tmp/{fname}").write_text(out, encoding="utf-8")
    print(out)
    print()
    print(f"  Log: /tmp/{fname}")


# ---------------- WAVE 1: Plan (read-only) ----------------

def wave1():
    L = []
    p = L.append
    p("# p57 / Step 10 -- WAVE 1: Plan (read-only)"); p("")
    profiles = frappe.db.sql("""
        select name, warehouse, cost_center, company from `tabPOS Profile`
        where disabled = 0 order by name
    """, as_dict=True)
    p(f"- Active POS Profiles: **{len(profiles)}**"); p("")

    outlet_map = {}
    for pp in profiles:
        outlet = _outlet_from_warehouse(pp["warehouse"])
        if not outlet:
            p(f"- :warning: `{pp['name']}` has no parseable warehouse, skipping")
            continue
        outlet_map.setdefault(outlet, []).append(pp["name"])

    p(f"- Distinct outlets: **{len(outlet_map)}**: {sorted(outlet_map.keys())}"); p("")

    p("## Account availability check")
    p("| Outlet | Mode | Resolved account | Status |")
    p("|--------|------|------------------|--------|")
    missing_accts = []
    for outlet in sorted(outlet_map.keys()):
        for mode in MODES:
            acct = _expected_account(mode, outlet)
            if acct:
                p(f"| {outlet} | {mode} | `{acct}` | :white_check_mark: |")
            else:
                p(f"| {outlet} | {mode} | (none found) | :x: |")
                missing_accts.append((outlet, mode))
    p("")
    if missing_accts:
        p(f"**{len(missing_accts)} account(s) not found.** Check the spelling variants "
          f"in OUTLET_ALIAS or add the missing accounts in CoA before continuing.")
        p("")

    p("## Mode of Payment plan")
    p("| Outlet | Mode | MOP name | Already exists? | Will link to account |")
    p("|--------|------|----------|-----------------|---------------------|")
    will_create = 0
    will_update = 0
    for outlet in sorted(outlet_map.keys()):
        for mode in MODES:
            mop = _mop_name(mode, outlet)
            acct = _expected_account(mode, outlet) or "(account missing)"
            mop_exists = frappe.db.exists("Mode of Payment", mop)
            if mop_exists:
                # check if linked already
                row = frappe.db.get_value("Mode of Payment Account",
                                          {"parent": mop, "company": COMPANY},
                                          "default_account")
                mark = "exists, account: " + (row or "(none)")
                will_update += 1 if row != acct else 0
            else:
                mark = "**will create**"
                will_create += 1
            p(f"| {outlet} | {mode} | {mop} | {mark} | {acct} |")
    p("")
    p(f"- Will create: **{will_create}** MOPs")
    p(f"- Will update: **{will_update}** existing MOPs")
    p("")

    p("## POS Profile rewire plan")
    p("| Profile | Outlet | Current `payments` rows | New `payments` rows |")
    p("|---------|--------|------------------------|---------------------|")
    for pp in profiles:
        outlet = _outlet_from_warehouse(pp["warehouse"])
        if not outlet:
            continue
        cur = frappe.db.sql("""
            select mode_of_payment from `tabPOS Payment Method`
            where parent = %s order by idx
        """, (pp["name"],), as_dict=True)
        cur_str = ", ".join(c["mode_of_payment"] for c in cur)
        new_str = ", ".join(_mop_name(m, outlet) for m in MODES)
        p(f"| {pp['name']} | {outlet} | {cur_str} | {new_str} |")
    p("")

    p("## Generic MOPs that Wave 4 will disable")
    for m in DISABLE_MOPS:
        exists = frappe.db.exists("Mode of Payment", m)
        en = frappe.db.get_value("Mode of Payment", m, "enabled") if exists else None
        p(f"- {m}: exists={bool(exists)}, currently enabled={en}")
    p("")
    p("Run `WAVE=2 LIVE=1` to start applying changes.")
    _save(L, "p57_step10_wave1.log")


# ---------------- WAVE 2: Create MOPs ----------------

def wave2(live: bool):
    L = []
    p = L.append
    p(f"# p57 / Step 10 -- WAVE 2: Create MOPs"); p("")
    p(f"- Mode: {'LIVE' if live else 'DRY-RUN'}"); p("")
    profiles = frappe.db.sql("""
        select distinct warehouse from `tabPOS Profile` where disabled = 0
    """, as_dict=True)
    outlets = sorted({_outlet_from_warehouse(r["warehouse"])
                      for r in profiles if r["warehouse"]})

    plan = []
    for outlet in outlets:
        for mode in MODES:
            mop = _mop_name(mode, outlet)
            acct = _expected_account(mode, outlet)
            if not acct:
                plan.append((outlet, mode, mop, "(none)", "SKIP: account not found"))
                continue
            plan.append((outlet, mode, mop, acct, "create_or_update"))

    p("## Plan")
    p("| Outlet | Mode | MOP | Account | Action |")
    p("|--------|------|-----|---------|--------|")
    for outlet, mode, mop, acct, action in plan:
        p(f"| {outlet} | {mode} | {mop} | {acct} | {action} |")
    p("")

    if not live:
        p("DRY-RUN -- no changes."); _save(L, "p57_step10_wave2.log"); return

    created, updated, skipped, failed = 0, 0, 0, []
    for outlet, mode, mop, acct, action in plan:
        if action.startswith("SKIP"):
            skipped += 1; continue
        try:
            if frappe.db.exists("Mode of Payment", mop):
                doc = frappe.get_doc("Mode of Payment", mop)
                # ensure the Mode of Payment Account row exists & points to acct
                found = False
                for row in doc.accounts:
                    if row.company == COMPANY:
                        if row.default_account != acct:
                            row.default_account = acct
                            updated += 1
                        found = True
                        break
                if not found:
                    doc.append("accounts", {
                        "company": COMPANY,
                        "default_account": acct,
                    })
                    updated += 1
                doc.save(ignore_permissions=True)
            else:
                doc = frappe.get_doc({
                    "doctype": "Mode of Payment",
                    "mode_of_payment": mop,
                    "enabled": 1,
                    "type": MODE_TYPE[mode],
                    "accounts": [{
                        "company": COMPANY,
                        "default_account": acct,
                    }],
                })
                doc.insert(ignore_permissions=True)
                created += 1
        except Exception as e:
            failed.append((mop, str(e)))
            p(f"- :x: {mop}: {e}")
    frappe.db.commit()
    p(f"- Created: {created}    Updated: {updated}    Skipped: {skipped}    Failed: {len(failed)}")
    _save(L, "p57_step10_wave2.log")


# ---------------- WAVE 3: Rewire POS Profiles ----------------

def wave3(live: bool):
    L = []
    p = L.append
    p(f"# p57 / Step 10 -- WAVE 3: Rewire POS Profiles"); p("")
    p(f"- Mode: {'LIVE' if live else 'DRY-RUN'}"); p("")

    profiles = frappe.db.sql("""
        select name, warehouse from `tabPOS Profile` where disabled = 0
        order by name
    """, as_dict=True)
    actions = []
    for pp in profiles:
        outlet = _outlet_from_warehouse(pp["warehouse"])
        if not outlet:
            actions.append((pp["name"], None, [], "SKIP: no warehouse"))
            continue
        target_mops = [_mop_name(m, outlet) for m in MODES]
        # verify all target MOPs exist
        missing = [m for m in target_mops if not frappe.db.exists("Mode of Payment", m)]
        if missing:
            actions.append((pp["name"], outlet, target_mops, f"SKIP: missing MOPs {missing}"))
            continue
        actions.append((pp["name"], outlet, target_mops, "rewire"))

    p("## Plan")
    p("| Profile | Outlet | Target MOPs | Action |")
    p("|---------|--------|-------------|--------|")
    for prof, outlet, mops, action in actions:
        p(f"| {prof} | {outlet} | {', '.join(mops)} | {action} |")
    p("")

    if not live:
        p("DRY-RUN -- no changes."); _save(L, "p57_step10_wave3.log"); return

    ok, skipped, failed = 0, 0, []
    for prof, outlet, target_mops, action in actions:
        if action.startswith("SKIP"):
            skipped += 1
            p(f"- :warning: {prof} -- {action}")
            continue
        try:
            doc = frappe.get_doc("POS Profile", prof)
            # Identify which is default; first one wins as default
            # Remove all existing payment rows
            doc.set("payments", [])
            for i, mop in enumerate(target_mops):
                doc.append("payments", {
                    "mode_of_payment": mop,
                    "default": 1 if i == 0 else 0,
                    "allow_in_returns": 1,
                })
            doc.save(ignore_permissions=True)
            ok += 1
            p(f"- :white_check_mark: rewired {prof} -> {target_mops}")
        except Exception as e:
            failed.append((prof, str(e)))
            p(f"- :x: {prof}: {e}")
    frappe.db.commit()
    p("")
    p(f"- Rewired: {ok}    Skipped: {skipped}    Failed: {len(failed)}")
    _save(L, "p57_step10_wave3.log")


# ---------------- WAVE 4: Disable generic MOPs ----------------

def wave4(live: bool):
    L = []
    p = L.append
    p(f"# p57 / Step 10 -- WAVE 4: Disable generic MOPs"); p("")
    p(f"- Mode: {'LIVE' if live else 'DRY-RUN'}"); p("")

    p("## Plan")
    p("| Generic MOP | Exists? | Currently enabled? | Will disable? |")
    p("|-------------|---------|--------------------|----|")
    plan = []
    for m in DISABLE_MOPS:
        exists = frappe.db.exists("Mode of Payment", m)
        en = frappe.db.get_value("Mode of Payment", m, "enabled") if exists else None
        will = bool(exists and en)
        plan.append((m, exists, en, will))
        p(f"| {m} | {bool(exists)} | {en} | {will} |")
    p("")

    if not live:
        p("DRY-RUN -- no changes."); _save(L, "p57_step10_wave4.log"); return

    ok, failed = 0, []
    for m, exists, en, will in plan:
        if not will:
            continue
        try:
            frappe.db.set_value("Mode of Payment", m, "enabled", 0)
            ok += 1
            p(f"- :white_check_mark: disabled `{m}`")
        except Exception as e:
            failed.append((m, str(e)))
            p(f"- :x: {m}: {e}")
    frappe.db.commit()
    p(f"- Disabled: {ok}    Failed: {len(failed)}")
    _save(L, "p57_step10_wave4.log")


# ---------------- WAVE 5: Journal Entry draft ----------------

def wave5(live: bool):
    L = []
    p = L.append
    p(f"# p57 / Step 10 -- WAVE 5: Journal Entry draft (Ikeja POS correction)"); p("")
    p(f"- Mode: {'LIVE' if live else 'DRY-RUN'}"); p("")

    wrong = "1503 - POS Incoming - Pedro - SCL"
    right = _resolve_account("POS", "Ikeja") or ""

    # Confirm both accounts exist
    if not frappe.db.exists("Account", wrong):
        p(f"**ABORT** -- wrong-side account `{wrong}` not found."); _save(L, "p57_step10_wave5.log"); return
    if not frappe.db.exists("Account", right):
        p(f"**ABORT** -- right-side account `{right}` not found in CoA. "
          f"Confirm the correct account naming for Ikeja POS Incoming and re-run."); _save(L, "p57_step10_wave5.log"); return

    # Re-compute the mis-posted total from data (don't hardcode)
    misposted = frappe.db.sql("""
        select sum(sip.amount) as total, count(distinct pi.name) as inv_count
        from `tabSales Invoice Payment` sip
        join `tabPOS Invoice` pi on pi.name = sip.parent
        where pi.docstatus = 1
          and pi.pos_profile = 'POS - Ikeja'
          and sip.mode_of_payment = 'POS'
          and sip.account = %s
    """, (wrong,), as_dict=True)
    amount = float(misposted[0]["total"] or 0)
    n_invs = misposted[0]["inv_count"] or 0
    p(f"- Mis-posted amount detected: **NGN {amount:,.2f}** across {n_invs} POS Invoice(s)"); p("")

    if amount <= 0:
        p("- :white_check_mark: nothing to correct."); _save(L, "p57_step10_wave5.log"); return

    p("## Planned Journal Entry (draft)")
    p(f"- Posting date: 2026-05-31")
    p(f"- Naming series: MC-COR-202605-")
    p(f"- Dr `{right}`  NGN {amount:,.2f}")
    p(f"- Cr `{wrong}`  NGN {amount:,.2f}")
    p(f"- User remark: \"Correction: ₦{amount:,.2f} of POS receipts at Ikeja outlet "
      f"were posted to Pedro's POS Incoming GL due to Mode of Payment default mis-configuration. "
      f"Routed correctly going forward via per-outlet MOPs (Step 10). Draft -- awaiting HOD Finance review.\"")
    p("")

    if not live:
        p("DRY-RUN -- no changes."); _save(L, "p57_step10_wave5.log"); return

    try:
        je = frappe.get_doc({
            "doctype": "Journal Entry",
            "voucher_type": "Journal Entry",
            "naming_series": "MC-COR-.YYYYMM.-",
            "posting_date": "2026-05-31",
            "company": COMPANY,
            "user_remark": (
                f"Correction: NGN {amount:,.2f} of POS receipts at Ikeja outlet "
                f"posted to Pedro POS Incoming GL due to MOP default mis-configuration. "
                f"Routing fixed via Step 10 per-outlet MOPs. Draft -- HOD Finance to review and submit."
            ),
            "accounts": [
                {
                    "account": right,
                    "debit_in_account_currency": amount,
                    "credit_in_account_currency": 0,
                },
                {
                    "account": wrong,
                    "debit_in_account_currency": 0,
                    "credit_in_account_currency": amount,
                },
            ],
        })
        je.insert(ignore_permissions=True)
        frappe.db.commit()
        p(f"- :white_check_mark: created JE draft `{je.name}` (NOT submitted -- HOD Finance review).")
    except Exception as e:
        frappe.db.rollback()
        p(f"- :x: failed to create JE: {e}")
        import traceback
        p("```"); p(traceback.format_exc()); p("```")

    _save(L, "p57_step10_wave5.log")


# ---------------- entrypoint ----------------

def main():
    wave = os.environ.get("WAVE", "").strip()
    live = os.environ.get("LIVE", "0") == "1"
    if wave == "1":
        wave1()
    elif wave == "2":
        wave2(live)
    elif wave == "3":
        wave3(live)
    elif wave == "4":
        wave4(live)
    elif wave == "5":
        wave5(live)
    else:
        print("Set WAVE=1|2|3|4|5 before running.")


main()
