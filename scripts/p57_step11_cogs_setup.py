"""
p57 / Step 11 -- COGS architecture (Option B + Cost Center per outlet).

Design decision (locked-in with user 2026-02):
  Per-outlet COGS *split* comes from Cost Center on POS Profiles, NOT from
  per-outlet expense GL accounts. ERPNext routes COGS via Item.item_defaults
  (one row per Company), so per-warehouse leaf accounts are infeasible without
  brittle custom server scripts. Cost Center dimension on each POS Profile
  produces the same per-outlet P&L visibility via the Profitability Analysis
  report -- zero custom code, survives upgrades.

What this script does (wave-based, idempotent):
  WAVE=1  PLAN        (read-only) -- shows what would be done
  WAVE=2  ACCOUNTS    creates the 3 leaf COGS accounts under
                      `8000 - 8499 - Cost Of Sales - SCL`
                          - 8101 - COGS - LPG Refill - SCL
                          - 8102 - COGS - Cylinders - SCL
                          - 8103 - COGS - Accessories - SCL
                      (idempotent: skips if already present)
  WAVE=3  ITEMS       sets Item Defaults.expense_account on every sales Item
                      according to its Item Group:
                          LPG / Refill / Gas  -> 8101
                          Cylinder            -> 8102
                          everything else     -> 8103 (default fallback)
  WAVE=4  AUDIT_CC    audits Cost Center field on each POS Profile -- reports
                      missing or wrong (per outlet). Read-only.
  WAVE=5  FIX_CC      sets POS Profile.cost_center to the matching outlet's
                      cost center (Sales and Marketing <outlet>). Idempotent.

Parameters:
    WAVE    "1" | "2" | "3" | "4" | "5". Required.
    LIVE    "1" to write. Default "0" (dry-run). Ignored for WAVE=1 and WAVE=4.

Run pattern (replace SHA):
    SHA=<commit-sha>
    cd ~/frappe-bench
    curl -fsSL \
      "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/$SHA/scripts/p57_step11_cogs_setup.py" \
      -o /tmp/p57s11.py
    export WAVE=1
    bench --site sungasmis.v.frappe.cloud execute \
      "(exec(open('/tmp/p57s11.py').read(), globals()) or (lambda **k: None))"
"""
from __future__ import annotations
from pathlib import Path
import os
import frappe

COMPANY = "SUNGAS COMPANY LIMITED"
COMPANY_ABBR = "SCL"

# Parent group account under which to create the 3 leaf COGS accounts.
# Discovered from p57_discover_cogs.py output:
COGS_PARENT = "8000 - 8499 - Cost Of Sales - SCL"

# Three leaf COGS accounts (code -- account_name -- maps-to-which-item-groups)
COGS_ACCOUNTS = [
    {
        "code": "8101",
        "name": "COGS - LPG Refill",
        "full": f"8101 - COGS - LPG Refill - {COMPANY_ABBR}",
        # Item Group name substrings that route here (lowercased match)
        "matches": ["lpg", "refill", "gas"],
    },
    {
        "code": "8102",
        "name": "COGS - Cylinders",
        "full": f"8102 - COGS - Cylinders - {COMPANY_ABBR}",
        "matches": ["cylinder"],
    },
    {
        "code": "8103",
        "name": "COGS - Accessories",
        "full": f"8103 - COGS - Accessories - {COMPANY_ABBR}",
        "matches": [],  # fallback
    },
]

# Outlet aliases used for Cost Center lookup (POS Profile warehouse vs CC name spelling)
OUTLET_ALIAS = {
    "Iju-Otta": ["Iju-Otta", "Iju-Ota"],
    "Ebutte":   ["Ebutte", "Ebute"],
    "Osi-Otta": ["Osi-Otta", "Osi-Ota"],
}


# ---------------- helpers ----------------

def _save(L, fname="p57_step11_cogs"):
    out = "\n".join(L)
    Path(f"/tmp/{fname}.log").write_text(out, encoding="utf-8")
    print(out)
    print()
    print(f"  Log: /tmp/{fname}.log")


def _route_for_item_group(group_name: str) -> dict:
    """Return the COGS_ACCOUNTS entry that best matches this item group."""
    g = (group_name or "").lower()
    for acct in COGS_ACCOUNTS:
        for kw in acct["matches"]:
            if kw in g:
                return acct
    return COGS_ACCOUNTS[-1]  # fallback = Accessories


def _outlet_from_warehouse(wh: str | None) -> str | None:
    if not wh:
        return None
    return wh.rsplit(" - ", 1)[0].strip() if " - " in wh else wh.strip()


def _find_cost_center(outlet: str) -> str | None:
    """Cost Center pattern: '<...> Sales and Marketing <outlet> - SCL'."""
    variants = OUTLET_ALIAS.get(outlet, [outlet])
    for v in variants:
        rows = frappe.get_all(
            "Cost Center",
            filters={
                "company": COMPANY, "is_group": 0,
                "cost_center_name": ["like", f"%Sales and Marketing {v}%"],
            },
            pluck="name", limit=1,
        )
        if rows:
            return rows[0]
        # Plain outlet name fallback
        rows = frappe.get_all(
            "Cost Center",
            filters={
                "company": COMPANY, "is_group": 0,
                "cost_center_name": ["like", f"%{v}%"],
            },
            pluck="name", limit=1,
        )
        if rows:
            return rows[0]
    return None


# ---------------- waves ----------------

def wave1_plan(L):
    p = L.append
    p("# p57 / Step 11 / WAVE 1 -- Plan (read-only)")
    p("")
    p(f"- Company: `{COMPANY}`")
    p(f"- Parent group account: `{COGS_PARENT}`")
    p("")

    # Parent exists?
    parent_exists = frappe.db.exists("Account", COGS_PARENT)
    p("## Parent group account check")
    if parent_exists:
        p(f"- :white_check_mark: `{COGS_PARENT}` exists.")
    else:
        p(f"- :x: `{COGS_PARENT}` NOT FOUND. WAVE 2 will fail unless you correct COGS_PARENT.")
        # Show all group expense accounts to help user pick the right one
        groups = frappe.db.sql("""
            select name from `tabAccount`
            where company = %s and is_group = 1 and root_type = 'Expense'
            order by name
        """, (COMPANY,), as_dict=True)
        p(f"  Available expense-root group accounts ({len(groups)}):")
        for g in groups:
            p(f"  - `{g['name']}`")
    p("")

    # Accounts plan
    p("## Accounts to be created (WAVE 2)")
    p("| Code | Account Name | Full Name | Status |")
    p("|------|--------------|-----------|--------|")
    for a in COGS_ACCOUNTS:
        status = "ALREADY EXISTS" if frappe.db.exists("Account", a["full"]) else "WILL CREATE"
        p(f"| {a['code']} | {a['name']} | `{a['full']}` | {status} |")
    p("")

    # Item Group routing preview
    p("## Item Group -> COGS routing (WAVE 3 preview)")
    groups = frappe.db.sql("""
        select name from `tabItem Group` where is_group = 0 order by name
    """, as_dict=True)
    routing = {}
    for g in groups:
        target = _route_for_item_group(g["name"])
        routing.setdefault(target["code"], []).append(g["name"])
    for code, names in routing.items():
        acct = next(a for a in COGS_ACCOUNTS if a["code"] == code)
        p(f"### -> `{acct['full']}` ({len(names)} group(s))")
        for n in names[:30]:
            p(f"- {n}")
        if len(names) > 30:
            p(f"- ... +{len(names) - 30} more")
    p("")

    # Items missing expense account
    items = frappe.db.sql("""
        select name, item_group from `tabItem`
        where disabled = 0 and is_sales_item = 1
        order by item_group, name
    """, as_dict=True)
    missing = []
    for it in items:
        ea = frappe.db.get_value(
            "Item Default", {"parent": it["name"], "company": COMPANY},
            "expense_account",
        )
        if not ea:
            missing.append(it)
    p(f"## Sales items missing Expense Account for {COMPANY}: **{len(missing)}** of {len(items)}")
    for it in missing[:25]:
        target = _route_for_item_group(it["item_group"])
        p(f"- `{it['name']}` (group=`{it['item_group']}`) -> `{target['full']}`")
    if len(missing) > 25:
        p(f"- ... +{len(missing) - 25} more")
    p("")

    # POS Profile cost-center audit preview
    p("## POS Profile Cost Center audit (WAVE 4 preview)")
    profs = frappe.get_all(
        "POS Profile",
        filters={"company": COMPANY, "disabled": 0},
        fields=["name", "warehouse", "cost_center"],
        order_by="name",
    )
    ok, missing_cc, mismatch_cc = 0, [], []
    for prof in profs:
        outlet = _outlet_from_warehouse(prof["warehouse"])
        expected = _find_cost_center(outlet) if outlet else None
        if not prof["cost_center"]:
            missing_cc.append((prof["name"], outlet, expected))
        elif expected and prof["cost_center"] != expected:
            mismatch_cc.append((prof["name"], outlet, prof["cost_center"], expected))
        else:
            ok += 1
    p(f"- :white_check_mark: OK (cost_center already set): {ok}")
    p(f"- :warning: Missing cost_center: {len(missing_cc)}")
    for n, o, e in missing_cc:
        p(f"  - `{n}` (outlet=`{o}`) -> expected `{e or '(not found)'}`")
    p(f"- :x: Mismatch (set but wrong outlet): {len(mismatch_cc)}")
    for n, o, c, e in mismatch_cc:
        p(f"  - `{n}` (outlet=`{o}`) currently=`{c}` expected=`{e}`")
    p("")
    p("---")
    p("Next: `WAVE=2 LIVE=1` to create the 3 COGS accounts.")


def wave2_accounts(L, live: bool):
    p = L.append
    p("# p57 / Step 11 / WAVE 2 -- Create COGS leaf accounts")
    p("")
    p(f"- Mode: {'LIVE' if live else 'DRY-RUN'}")
    p(f"- Parent: `{COGS_PARENT}`")
    p("")

    if not frappe.db.exists("Account", COGS_PARENT):
        p(f"**ABORT** -- parent group `{COGS_PARENT}` not found. Run WAVE 1 to see options.")
        return

    parent_doc = frappe.get_doc("Account", COGS_PARENT)
    created, skipped, failed = 0, 0, []
    for a in COGS_ACCOUNTS:
        if frappe.db.exists("Account", a["full"]):
            skipped += 1
            p(f"- skip `{a['full']}` (already exists)")
            continue
        if not live:
            p(f"- WOULD CREATE `{a['full']}` under `{COGS_PARENT}`")
            continue
        try:
            doc = frappe.get_doc({
                "doctype": "Account",
                "account_name": a["name"],
                "account_number": a["code"],
                "parent_account": COGS_PARENT,
                "company": COMPANY,
                "account_type": "Cost of Goods Sold",
                "root_type": "Expense",
                "report_type": "Profit and Loss",
                "is_group": 0,
                "account_currency": parent_doc.account_currency or "NGN",
            })
            doc.insert(ignore_permissions=True)
            created += 1
            p(f"- :white_check_mark: created `{doc.name}`")
        except Exception as e:
            failed.append((a["full"], str(e)))
            p(f"- :x: `{a['full']}`: {e}")
    if live:
        frappe.db.commit()
    p("")
    p(f"**Created**: {created}    **Skipped**: {skipped}    **Failed**: {len(failed)}")


def wave3_items(L, live: bool):
    p = L.append
    p("# p57 / Step 11 / WAVE 3 -- Set Item Defaults expense_account")
    p("")
    p(f"- Mode: {'LIVE' if live else 'DRY-RUN'}")
    p("")

    # Pre-check: all 3 COGS accounts exist?
    missing_accts = [a["full"] for a in COGS_ACCOUNTS if not frappe.db.exists("Account", a["full"])]
    if missing_accts:
        p("**ABORT** -- the following COGS accounts do not exist (run WAVE 2 first):")
        for n in missing_accts:
            p(f"  - `{n}`")
        return

    items = frappe.db.sql("""
        select name, item_group from `tabItem`
        where disabled = 0 and is_sales_item = 1
        order by item_group, name
    """, as_dict=True)
    p(f"- Sales items in scope: {len(items)}")

    by_route = {a["code"]: 0 for a in COGS_ACCOUNTS}
    updated, unchanged, failed = 0, 0, []

    for it in items:
        target = _route_for_item_group(it["item_group"])
        target_acct = target["full"]
        try:
            doc = frappe.get_doc("Item", it["name"])
            row = next((r for r in doc.item_defaults if r.company == COMPANY), None)
            current = (row.expense_account if row else None)
            if current == target_acct:
                unchanged += 1
                continue
            if not live:
                p(f"- WOULD set `{it['name']}` (group=`{it['item_group']}`) -> `{target_acct}` "
                  f"(currently=`{current or '(unset)'}`)")
                by_route[target["code"]] += 1
                continue
            if row:
                row.expense_account = target_acct
            else:
                doc.append("item_defaults", {
                    "company": COMPANY,
                    "expense_account": target_acct,
                })
            doc.save(ignore_permissions=True)
            updated += 1
            by_route[target["code"]] += 1
        except Exception as e:
            failed.append((it["name"], str(e)))
    if live:
        frappe.db.commit()

    p("")
    p("## Routing summary")
    for a in COGS_ACCOUNTS:
        p(f"- `{a['full']}` -> {by_route[a['code']]} items")
    p("")
    p(f"**Updated**: {updated}    **Unchanged**: {unchanged}    **Failed**: {len(failed)}")
    for n, e in failed[:10]:
        p(f"- :x: {n}: {e}")
    if len(failed) > 10:
        p(f"- ... +{len(failed) - 10} more failures (see log)")


def wave4_audit_cc(L):
    p = L.append
    p("# p57 / Step 11 / WAVE 4 -- POS Profile cost_center audit (read-only)")
    p("")
    profs = frappe.get_all(
        "POS Profile",
        filters={"company": COMPANY, "disabled": 0},
        fields=["name", "warehouse", "cost_center"],
        order_by="name",
    )
    p(f"- POS Profiles in scope: {len(profs)}")
    p("")
    p("| Profile | Outlet | Warehouse | Current CC | Expected CC | Status |")
    p("|---------|--------|-----------|------------|-------------|--------|")
    ok, missing_cc, mismatch_cc, no_expected = 0, 0, 0, 0
    for prof in profs:
        outlet = _outlet_from_warehouse(prof["warehouse"])
        expected = _find_cost_center(outlet) if outlet else None
        cur = prof["cost_center"] or ""
        if not expected:
            status = ":grey_question: NO CC FOUND FOR OUTLET"
            no_expected += 1
        elif not cur:
            status = ":warning: MISSING (will set in WAVE 5)"
            missing_cc += 1
        elif cur == expected:
            status = ":white_check_mark: OK"
            ok += 1
        else:
            status = ":x: MISMATCH (will fix in WAVE 5)"
            mismatch_cc += 1
        p(f"| `{prof['name']}` | {outlet} | `{prof['warehouse']}` | "
          f"`{cur or '(unset)'}` | `{expected or '(unknown)'}` | {status} |")
    p("")
    p(f"**OK**: {ok}    **Missing**: {missing_cc}    **Mismatch**: {mismatch_cc}    "
      f"**No expected CC**: {no_expected}")


def wave5_fix_cc(L, live: bool):
    p = L.append
    p("# p57 / Step 11 / WAVE 5 -- Set POS Profile cost_center per outlet")
    p("")
    p(f"- Mode: {'LIVE' if live else 'DRY-RUN'}")
    p("")
    profs = frappe.get_all(
        "POS Profile",
        filters={"company": COMPANY, "disabled": 0},
        fields=["name", "warehouse", "cost_center"],
        order_by="name",
    )
    set_count, skip, failed = 0, 0, []
    for prof in profs:
        outlet = _outlet_from_warehouse(prof["warehouse"])
        expected = _find_cost_center(outlet) if outlet else None
        if not expected:
            p(f"- :grey_question: skip `{prof['name']}` (outlet=`{outlet}`) -- no Cost Center found")
            skip += 1
            continue
        if prof["cost_center"] == expected:
            skip += 1
            continue
        if not live:
            p(f"- WOULD set `{prof['name']}` cost_center=`{expected}` "
              f"(currently=`{prof['cost_center'] or '(unset)'}`)")
            continue
        try:
            doc = frappe.get_doc("POS Profile", prof["name"])
            doc.cost_center = expected
            # Also set write_off_cost_center to keep it consistent
            doc.write_off_cost_center = expected
            doc.save(ignore_permissions=True)
            set_count += 1
            p(f"- :white_check_mark: `{prof['name']}` -> `{expected}`")
        except Exception as e:
            failed.append((prof["name"], str(e)))
            p(f"- :x: `{prof['name']}`: {e}")
    if live:
        frappe.db.commit()
    p("")
    p(f"**Set**: {set_count}    **Skipped/OK**: {skip}    **Failed**: {len(failed)}")


# ---------------- entry ----------------

def main():
    L = []
    wave = os.environ.get("WAVE", "").strip()
    live = os.environ.get("LIVE", "0") == "1"
    if wave == "1":
        wave1_plan(L)
    elif wave == "2":
        wave2_accounts(L, live)
    elif wave == "3":
        wave3_items(L, live)
    elif wave == "4":
        wave4_audit_cc(L)
    elif wave == "5":
        wave5_fix_cc(L, live)
    else:
        L.append("ERROR: set WAVE=1|2|3|4|5 (and LIVE=1 for write waves).")
    _save(L, fname=f"p57_step11_wave{wave or 'X'}")


main()
