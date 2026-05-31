"""
p57 / Step 10 -- Discover actual GL account naming for per-outlet receipts.

Searches the Chart of Accounts for:
  - All non-group accounts under common cash/POS/transfer parents
  - All accounts containing "Cash Sales", "POS Incoming", "Incoming Transfer"
    (regardless of position in name)
  - All accounts ending in a given outlet name -- for the 21 outlets

Read-only.
"""
from __future__ import annotations
from pathlib import Path
import frappe

COMPANY = "SUNGAS COMPANY LIMITED"
OUTLETS = ['Asaba', 'Aseese', 'Bolade', 'Ebutte', 'Ekehuan', 'Eleme', 'Idokpa',
           'Idowina', 'Ijoko', 'Iju-Otta', 'Ikeja', 'Itele', 'Maba', 'Mafoluku',
           'Okhuoromi', 'Osi-Otta', 'Oworo', 'Pedro', 'Reclamation', 'Sefu',
           'Upper Mission']
KEYWORDS = ["Cash Sales", "POS Incoming", "Incoming Transfer",
            "Cash", "POS", "Transfer", "Card"]


def main():
    L = []
    p = L.append
    p("# p57 / Step 10 -- Discover real GL account naming")
    p("")

    # 1) Accounts containing each keyword
    p("## 1. Accounts containing each keyword (company=SCL only, non-group)")
    for kw in KEYWORDS:
        rows = frappe.db.sql("""
            select name, account_name, parent_account
            from `tabAccount`
            where company = %s and disabled = 0 and is_group = 0
              and (account_name like %s or name like %s)
            order by name
        """, (COMPANY, f"%{kw}%", f"%{kw}%"), as_dict=True)
        p(f"### Keyword: `{kw}` -- {len(rows)} match(es)")
        if not rows:
            p("- (none)")
        else:
            p("| Account | Parent |")
            p("|---------|--------|")
            for r in rows[:40]:
                p(f"| `{r['name']}` | {r['parent_account']} |")
            if len(rows) > 40:
                p(f"| ... +{len(rows) - 40} more ... |")
        p("")

    # 2) For each outlet, find all accounts that mention it
    p("## 2. Accounts mentioning each outlet")
    for outlet in OUTLETS:
        rows = frappe.db.sql("""
            select name from `tabAccount`
            where company = %s and disabled = 0 and is_group = 0
              and (name like %s or account_name like %s)
            order by name
        """, (COMPANY, f"%{outlet}%", f"%{outlet}%"), as_dict=True)
        p(f"### Outlet: `{outlet}` -- {len(rows)} account(s)")
        if not rows:
            p("- (none)")
        else:
            for r in rows[:15]:
                p(f"- `{r['name']}`")
            if len(rows) > 15:
                p(f"- ... +{len(rows) - 15} more ...")
        p("")

    # 3) Recommended approach
    p("## 3. Approach")
    p("Compare keyword groups in section 1 to determine the real prefix +")
    p("the slot position of outlet in the name. Tell me the pattern and I'll")
    p("update Step 10 to use it. Common patterns:")
    p("- `1101 - Cash Sales - <Outlet> - SCL`  (what the script assumed)")
    p("- `Cash Sales <Outlet> - SCL`           (no leading code)")
    p("- `<Outlet> - Cash Sales - SCL`")
    p("- Or accounts grouped under a parent like `Cash In Hand - SCL` with")
    p("  outlet sub-accounts")
    p("")

    out = "\n".join(L)
    Path("/tmp/p57_acct_discover.log").write_text(out, encoding="utf-8")
    print(out)
    print()
    print(f"  Log: /tmp/p57_acct_discover.log")


main()
