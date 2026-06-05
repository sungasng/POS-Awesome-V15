"""p57_audit_vat_setup.py
==========================
Read-only auditor: report the current state of VAT/tax setup before we add
anything. Run this first so we don't create duplicate accounts/templates.

Reports:
  1. All GL accounts with "VAT" or "Tax" in the name (the candidate output
     VAT liability + input VAT receivable accounts).
  2. All Sales Taxes and Charges Templates (these are the per-invoice
     templates ERPNext picks at sale time).
  3. All Item Tax Templates (these set per-item or per-item-group tax rates).
  4. Per Item Group: how many items + whether the group has a tax assignment.
  5. The 5 most-recent POS Invoices: do they have any tax rows? (tells us if
     the current receipt already prints a VAT line or not.)

Run:
  bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/p57_vat_audit.py').read())"
"""
import frappe  # type: ignore # noqa: F401


def section(title):
    print(f"\n{'=' * 6} {title} {'=' * 6}")


def main():
    section("1. GL accounts with 'VAT' or 'Tax' in the name")
    accts = frappe.db.sql(
        """
        SELECT name, account_type, root_type, is_group, disabled
        FROM `tabAccount`
        WHERE (name LIKE '%%VAT%%' OR name LIKE '%%Tax%%')
          AND disabled = 0
        ORDER BY name
        """,
        as_dict=True,
    )
    if not accts:
        print("  (none found — VAT accounts may need to be created)")
    for a in accts:
        flags = "GROUP" if a.is_group else "LEAF"
        print(f"  [{a.root_type:7s}] [{flags}] {a.name:60s}  type={a.account_type or '-'}")

    section("2. Sales Taxes and Charges Templates")
    templates = frappe.get_all(
        "Sales Taxes and Charges Template",
        fields=["name", "company", "disabled", "is_default"],
        order_by="company, name",
    )
    if not templates:
        print("  (none)")
    for t in templates:
        flags = "DEFAULT" if t.is_default else ""
        disabled = "DISABLED" if t.disabled else ""
        print(f"  {t.name:60s}  company={t.company}  {flags} {disabled}")
        rows = frappe.db.sql(
            """SELECT charge_type, account_head, rate, description
               FROM `tabSales Taxes and Charges` WHERE parent = %s ORDER BY idx""",
            (t.name,),
            as_dict=True,
        )
        for r in rows:
            print(f"      - {r.charge_type:20s} {r.account_head:55s} rate={r.rate}  desc={r.description}")

    section("3. Item Tax Templates")
    itts = frappe.get_all(
        "Item Tax Template",
        fields=["name", "company", "disabled"],
        order_by="company, name",
    )
    if not itts:
        print("  (none — we will create per-item-group templates)")
    for t in itts:
        print(f"  {t.name:60s}  company={t.company}  disabled={t.disabled}")
        rows = frappe.db.sql(
            """SELECT tax_type, tax_rate FROM `tabItem Tax Template Detail`
               WHERE parent = %s ORDER BY idx""",
            (t.name,),
            as_dict=True,
        )
        for r in rows:
            print(f"      - {r.tax_type:55s} rate={r.tax_rate}")

    section("4. Item Groups and tax linkage")
    groups = frappe.db.sql(
        """
        SELECT
            ig.name,
            ig.is_group,
            (SELECT COUNT(*) FROM `tabItem` i WHERE i.item_group = ig.name AND i.disabled = 0) AS item_count,
            (SELECT GROUP_CONCAT(igt.item_tax_template)
               FROM `tabItem Tax` igt
               WHERE igt.parent = ig.name AND igt.parenttype = 'Item Group') AS taxes
        FROM `tabItem Group` ig
        WHERE ig.is_group = 0
        ORDER BY ig.name
        """,
        as_dict=True,
    )
    for g in groups:
        print(f"  {g.name:30s}  items={g.item_count:4d}  taxes={g.taxes or '-'}")

    section("5. Recent POS Invoices — do any have tax rows?")
    invoices = frappe.get_all(
        "POS Invoice",
        fields=["name", "grand_total", "total_taxes_and_charges", "pos_profile"],
        order_by="posting_date desc, posting_time desc",
        limit=5,
    )
    if not invoices:
        # fall back to Sales Invoice if no POS Invoice
        invoices = frappe.get_all(
            "Sales Invoice",
            fields=["name", "grand_total", "total_taxes_and_charges", "pos_profile"],
            filters={"is_pos": 1},
            order_by="posting_date desc, posting_time desc",
            limit=5,
        )
    for inv in invoices:
        print(f"  {inv.name:25s}  grand_total={inv.grand_total}  tax_total={inv.total_taxes_and_charges or 0}  profile={inv.pos_profile}")

    section("6. Default company")
    default_company = frappe.defaults.get_global_default("company") or "?"
    print(f"  Default company: {default_company}")
    companies = frappe.get_all("Company", fields=["name", "default_currency", "country"])
    for c in companies:
        print(f"    {c.name}  currency={c.default_currency}  country={c.country}")

    print()


# _BENCH_EXEC_FIX: bench execute "exec(...)" runs scripts with separate
# globals/locals dicts, so module-level functions can't see other module-level
# helpers. Copying locals -> globals before invoking main() fixes the scope.
globals().update(locals())
main()
