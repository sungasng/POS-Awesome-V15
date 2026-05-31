"""
p57: Discover Cost of Goods / Direct Cost accounts in CoA.
Read-only.
"""
import frappe

COMPANY = "SUNGAS COMPANY LIMITED"


def main():
    print(f"# Cost / Expense account discovery for {COMPANY}")
    print()
    rows = frappe.db.sql("""
        select name, account_name, account_type, root_type, parent_account
        from `tabAccount`
        where company = %s and disabled = 0 and is_group = 0
          and (
            account_name like '%%Cost%%' or
            account_name like '%%COGS%%' or
            account_name like '%%Direct%%' or
            account_name like '%%Stock Adjustment%%' or
            account_name like '%%Stock Variance%%' or
            account_type in ('Cost of Goods Sold','Expense Account','Direct Expense',
                             'Stock Adjustment') or
            (root_type = 'Expense' and parent_account like '%%Direct%%')
          )
        order by name
    """, (COMPANY,), as_dict=True)
    print(f"Found **{len(rows)}** candidate accounts:")
    print()
    print("| Account | Type | Root | Parent |")
    print("|---------|------|------|--------|")
    for r in rows:
        print(f"| `{r['name']}` | {r['account_type'] or '-'} | {r['root_type']} | "
              f"{r['parent_account'] or '-'} |")
    print()

    # Also list all top-level Expense parents to see the structure
    parents = frappe.db.sql("""
        select name, account_name from `tabAccount`
        where company = %s and is_group = 1 and root_type = 'Expense'
        order by name
    """, (COMPANY,), as_dict=True)
    print(f"## Top-level Expense group accounts ({len(parents)})")
    for r in parents:
        print(f"- `{r['name']}`")
    print()

    # Same for any 'Stock'-type expense
    stock_accts = frappe.db.sql("""
        select name, account_type from `tabAccount`
        where company = %s and disabled = 0 and is_group = 0
          and account_type in ('Stock', 'Stock Received But Not Billed',
                               'Stock Adjustment', 'Cost of Goods Sold')
        order by account_type, name limit 50
    """, (COMPANY,), as_dict=True)
    print(f"## Accounts of stock/cogs account_type ({len(stock_accts)})")
    for r in stock_accts:
        print(f"- `{r['name']}` (type={r['account_type']})")


main()
