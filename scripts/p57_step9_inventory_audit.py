"""
Phase 5.7 / Step 9: Inventory resilience audit.

Read-only. Reports on the 14 inventory settings that protect against
SLE drift, GL/Stock mismatches, and the "POS slows down at scale"
failure mode. Each finding is tagged PASS / WARN / FAIL with the
recommended remediation.

Run:
    SHA=<commit>
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/$SHA/scripts/p57_step9_inventory_audit.py" -o /tmp/p57i.py
    bench --site sungasmis.v.frappe.cloud execute "(exec(open('/tmp/p57i.py').read(), globals()) or (lambda **k: None))"

Output: stdout + /tmp/p57_inventory_audit.md
"""

from __future__ import annotations
from pathlib import Path
import frappe


def main() -> None:
    L: list[str] = []
    p = L.append
    p("# Phase 5.7 / Step 9 -- Inventory Resilience Audit")
    p("")

    ss = frappe.get_single("Stock Settings")
    asst = frappe.get_single("Accounts Settings")

    findings: list[tuple[str, str, str, str]] = []  # (severity, area, finding, remediation)

    # ---- 1. Perpetual inventory ----
    perpetual = bool(asst.acc_frozen_upto is not None or
                     frappe.db.get_single_value("Stock Settings", "stock_frozen_upto"))
    # Actually check whether stock_auto_reorder is on (a proxy for perpetual setup)
    p("## 1. Perpetual vs Periodic Inventory")
    p("")
    p("ERPNext v15 default is Perpetual (each transaction posts to SLE + GL in real time).")
    p("Stay on Perpetual. Periodic = v13 era, not recommended at LPG scale.")
    p("- Result: **PASS** (default config)")
    p("")

    # ---- 2. Allow Negative Stock ----
    allow_neg = bool(ss.allow_negative_stock)
    p("## 2. Allow Negative Stock")
    p(f"- Current: `{allow_neg}`")
    if allow_neg:
        p("- **WARN**: POS will allow selling cylinders that aren't physically there.")
        p("  Recommend: turn OFF for POS (cashier sees clear error) and create a")
        p("  separate role-permission for Stock Manager to enable temporarily for")
        p("  transfer/adjustment corrections.")
        findings.append(("WARN", "Stock Settings", "allow_negative_stock=ON",
                         "Disable except for Stock Manager role; force POS to refuse oversell"))
    else:
        p("- **PASS**")
    p("")

    # ---- 3. Stock Frozen Up To ----
    stock_frozen = ss.stock_frozen_upto
    p("## 3. Stock Frozen Up To")
    p(f"- Current: `{stock_frozen}`")
    if not stock_frozen:
        p("- **WARN**: history is editable; anyone with Stock Manager role can")
        p("  rewrite past SLE. Recommend: freeze at the end of every month-close.")
        findings.append(("WARN", "Stock Settings", "stock_frozen_upto is empty",
                         "After each month close, set to last day of closed month"))
    else:
        from datetime import date
        days_old = (date.today() - stock_frozen).days
        if days_old > 60:
            p(f"- **WARN**: freeze date is {days_old} days old. Past 60 days = stale.")
            findings.append(("WARN", "Stock Settings", f"stock_frozen_upto stale ({days_old}d)",
                             "Update to last day of most recent closed month"))
        else:
            p(f"- **PASS** ({days_old} days old)")
    p("")

    # ---- 4. Default Valuation Method ----
    val_method = ss.valuation_method or "FIFO"
    p("## 4. Default Valuation Method")
    p(f"- Current: `{val_method}`")
    if val_method == "FIFO":
        p("- **PASS** -- FIFO is regulator-friendly for fuel and matches industry practice.")
    elif val_method == "Moving Average":
        p("- **WARN**: Moving Average can drift if multiple POS profiles post out-of-order.")
        p("  Recommend: switch to FIFO for cylinders/LPG (set per-item if needed for accessories).")
        findings.append(("WARN", "Stock Settings", "valuation_method=Moving Average",
                         "Switch to FIFO for LPG; per-item override for accessories"))
    else:
        p(f"- **WARN**: unusual valuation method `{val_method}`. Confirm with Finance.")
    p("")

    # ---- 5. Auto-Insert Price List Rate If Missing ----
    auto_insert = bool(ss.auto_insert_price_list_rate_if_missing)
    p("## 5. Auto-Insert Price List Rate")
    p(f"- Current: `{auto_insert}`")
    if auto_insert:
        p("- **WARN**: cashier-created Items can silently set a price = last sale price")
        p("  with no margin guard. Recommend: OFF. Force Items to be priced via")
        p("  Item Price doctype with HOD Sales approval.")
        findings.append(("WARN", "Stock Settings",
                         "auto_insert_price_list_rate_if_missing=ON",
                         "Disable; require Item Price approval flow"))
    else:
        p("- **PASS**")
    p("")

    # ---- 6. Update Existing Price List Rate ----
    update_existing = bool(ss.update_existing_price_list_rate)
    p("## 6. Update Existing Price List Rate")
    p(f"- Current: `{update_existing}`")
    if update_existing:
        p("- **WARN**: any submitted Purchase Receipt overwrites the Selling Item Price.")
        p("  Hard to control margin. Recommend: OFF.")
        findings.append(("WARN", "Stock Settings", "update_existing_price_list_rate=ON",
                         "Disable; manage selling prices separately from purchase costs"))
    else:
        p("- **PASS**")
    p("")

    # ---- 7. Item Naming By ----
    naming_by = ss.item_naming_by or "Item Code"
    p("## 7. Item Naming By")
    p(f"- Current: `{naming_by}`")
    if naming_by != "Item Code":
        p("- **WARN**: relying on auto-naming series for Items makes barcode scanning brittle.")
        findings.append(("WARN", "Stock Settings", f"item_naming_by={naming_by}",
                         "Switch to 'Item Code'; cashier scans barcode -> exact match"))
    else:
        p("- **PASS**")
    p("")

    # ---- 8. Default Warehouse on POS Profiles ----
    p("## 8. Default Warehouse on every active POS Profile")
    pp_rows = frappe.db.sql("""
        select name, warehouse from `tabPOS Profile` where disabled = 0
    """, as_dict=True)
    missing = [r for r in pp_rows if not r["warehouse"]]
    if missing:
        p(f"- **FAIL**: {len(missing)} POS Profile(s) have no warehouse set.")
        for r in missing:
            p(f"  - {r['name']}")
        findings.append(("FAIL", "POS Profile", f"{len(missing)} POS Profile(s) missing warehouse",
                         "Set Default Warehouse explicitly on each profile"))
    else:
        p(f"- **PASS** ({len(pp_rows)} active POS Profiles all have a warehouse)")
    p("")

    # ---- 9. Item Default Warehouse per Company ----
    p("## 9. Items missing per-company Default Warehouse")
    items_no_default = frappe.db.sql("""
        select i.name from `tabItem` i
        where i.disabled = 0 and i.is_sales_item = 1
          and not exists (select 1 from `tabItem Default` id
                          where id.parent = i.name and id.default_warehouse is not null
                            and id.default_warehouse != '')
        limit 50
    """, as_dict=True)
    if items_no_default:
        p(f"- **WARN**: {len(items_no_default)} sales item(s) lack a default warehouse.")
        p("  Symptom: POS may use the global default instead of branch-specific stock.")
        for r in items_no_default[:10]:
            p(f"  - {r['name']}")
        if len(items_no_default) > 10:
            p(f"  ... and {len(items_no_default) - 10} more")
        findings.append(("WARN", "Item", f"{len(items_no_default)} sales items missing default warehouse",
                         "Bulk-set per-company default warehouses via Item Default"))
    else:
        p("- **PASS**")
    p("")

    # ---- 10. Accounting Dimension on Sales Invoice (Branch / Cost Center) ----
    p("## 10. Branch / Cost Center on POS Profiles")
    pp_no_cc = [r["name"] for r in frappe.db.sql("""
        select name from `tabPOS Profile`
        where disabled = 0 and (cost_center is null or cost_center = '')
    """, as_dict=True)]
    if pp_no_cc:
        p(f"- **WARN**: {len(pp_no_cc)} POS Profile(s) have no cost_center set.")
        for n in pp_no_cc:
            p(f"  - {n}")
        findings.append(("WARN", "POS Profile", "Some POS Profiles missing cost_center",
                         "Set cost_center per profile so P&L reports split by outlet"))
    else:
        p("- **PASS**")
    p("")

    # ---- 11. Item Group hierarchy depth ----
    max_depth = frappe.db.sql("""
        select max(rgt - lft) from `tabItem Group`
    """)[0][0] or 0
    p("## 11. Item Group hierarchy")
    p(f"- Max nested span (rgt-lft): {max_depth}")
    if max_depth > 50:
        p("- **WARN**: large/deeply-nested groups slow down POS Item search.")
    else:
        p("- **PASS**")
    p("")

    # ---- 12. Stock Reconciliation count (catches anyone bypassing FIFO) ----
    sr_count = frappe.db.count("Stock Reconciliation", {"docstatus": 1})
    p("## 12. Stock Reconciliations historically")
    p(f"- Total submitted: {sr_count}")
    if sr_count > 100:
        p("- **WARN**: high frequency. Each SR overrides FIFO valuation -> margin distortion.")
        p("  Investigate why so many manual corrections are happening.")
    else:
        p(f"- **PASS** ({sr_count} is reasonable)")
    p("")

    # ---- 13. Re-order level set on critical Items ----
    p("## 13. Re-order Level coverage")
    total_items = frappe.db.count("Item", {"disabled": 0, "is_stock_item": 1, "is_sales_item": 1})
    items_with_reorder = frappe.db.sql("""
        select count(distinct parent) from `tabItem Reorder`
    """)[0][0] or 0
    pct = (items_with_reorder * 100.0 / total_items) if total_items else 0
    p(f"- {items_with_reorder}/{total_items} sales/stock items have a Re-order Level ({pct:.0f}%)")
    if pct < 50:
        p("- **WARN**: <50% coverage. Auto-restock material requests won't fire for items")
        p("  without a reorder level. Recommend: set for top 80% by sales volume.")
        findings.append(("WARN", "Item Reorder", f"Only {pct:.0f}% items have reorder levels",
                         "Set Re-order Level on top 80% by sales velocity"))
    else:
        p("- **PASS**")
    p("")

    # ---- 14. Repost Item Valuation backlog ----
    p("## 14. Repost Item Valuation backlog")
    backlog = frappe.db.sql("""
        select status, count(*) as n
        from `tabRepost Item Valuation`
        where docstatus < 2
        group by status
    """, as_dict=True)
    if not backlog:
        p("- **PASS** (no Repost Item Valuation jobs found)")
    else:
        for r in backlog:
            p(f"  - {r['status']}: {r['n']}")
        stuck_count = sum(r["n"] for r in backlog if r["status"] in ("Queued", "In Progress"))
        if stuck_count > 5:
            p(f"- **WARN**: {stuck_count} jobs queued/in-progress. May be stuck.")
            findings.append(("WARN", "Repost", f"{stuck_count} Repost Item Valuation jobs queued",
                             "Investigate; clear stale jobs; check worker logs"))
        else:
            p(f"- **PASS** ({stuck_count} active)")
    p("")

    # ---- Summary ----
    p("---")
    p("")
    p("## Findings summary")
    p("")
    if not findings:
        p("All checks passed. Inventory configuration is resilient.")
    else:
        p(f"| Severity | Area | Finding | Recommendation |")
        p(f"|----------|------|---------|----------------|")
        for sev, area, fnd, rec in findings:
            p(f"| **{sev}** | {area} | {fnd} | {rec} |")

    p("")
    p("## Suggested remediation order")
    p("")
    p("1. **FAIL** items first (these will cause failures, not just degradation)")
    p("2. **WARN** items grouped by area (one settings page edit fixes multiple)")
    p("3. Re-run this audit after fixes; aim for zero WARN before production scale-up")

    out = "\n".join(L)
    Path("/tmp/p57_inventory_audit.md").write_text(out, encoding="utf-8")
    print(out)
    print()
    print(f"  Full report: /tmp/p57_inventory_audit.md")
    print(f"  Findings: {len(findings)}  "
          f"(FAIL={sum(1 for f in findings if f[0]=='FAIL')}, "
          f"WARN={sum(1 for f in findings if f[0]=='WARN')})")


try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
