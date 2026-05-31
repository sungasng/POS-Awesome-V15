"""
Quick: list existing leaf codes under each candidate parent group, so we can pick
free numbers for the variance accounts.
"""
from __future__ import annotations
from pathlib import Path
import frappe

COMPANY = "SUNGAS COMPANY LIMITED"

PARENTS = [
    "2600 - 2699 - Other receivables - SCL",
    "6200 - Other Payables - SCL",
    "9200 - 9499 - Other Operating Expense - SCL",
    "7200 - Other Income - SCL",
]


def main():
    L = []
    p = L.append
    p("# Free-code discovery under candidate parents")
    p("")
    for parent in PARENTS:
        p(f"## `{parent}`")
        if not frappe.db.exists("Account", parent):
            p("- :x: parent not found")
            p("")
            continue
        rows = frappe.db.sql("""
            select name, account_number from `tabAccount`
            where parent_account = %s and company = %s
            order by account_number, name
        """, (parent, COMPANY), as_dict=True)
        if not rows:
            p("- (no children)")
        else:
            p("| Code | Account |")
            p("|------|---------|")
            for r in rows:
                p(f"| {r['account_number'] or '-'} | `{r['name']}` |")
        # Also scan globally for any account with codes in plausible ranges
        # adjacent to this parent
        p("")
    p("---")
    p("## All account_numbers used company-wide (for collision checking)")
    used = frappe.db.sql("""
        select account_number, name
        from `tabAccount`
        where company = %s and account_number is not null and account_number != ''
        order by cast(account_number as unsigned), account_number
    """, (COMPANY,), as_dict=True)
    p(f"- {len(used)} accounts with codes set")
    # Just print the unique codes
    codes = sorted({r['account_number'] for r in used})
    p(f"- Used codes: {', '.join(codes[:100])}")
    if len(codes) > 100:
        p(f"  ... +{len(codes)-100} more")
    out = "\n".join(L)
    Path("/tmp/p57_discover_freecodes.log").write_text(out, encoding="utf-8")
    print(out)


main()
