"""
Phase 5.7 -- POS hardening scheduled tasks.

Registered in posawesome/hooks.py scheduler_events.
"""
from __future__ import annotations
import frappe


STUCK_THRESHOLD_MINUTES = 10
RETRY_NOTIFY_ROLES      = ["Accounts Manager", "POS Manager"]


def retry_stuck_pos_invoices() -> None:
    """Cron */5 * * * * -- retry submit on Draft POS Invoices stuck >10min.

    Triggers if queue worker died mid-submit, or if a network blip rolled
    back the transaction but the job runner didn't requeue.
    """
    rows = frappe.db.sql("""
        select name from `tabSales Invoice`
        where docstatus = 0 and is_pos = 1
          and coalesce(posa_is_printed, 0) = 1
          and TIMESTAMPDIFF(MINUTE, creation, NOW()) >= %s
        order by creation
        limit 100
    """, (STUCK_THRESHOLD_MINUTES,), as_dict=True)

    if not rows:
        return

    still_stuck: list[str] = []
    for r in rows:
        try:
            doc = frappe.get_doc("Sales Invoice", r["name"])
            if doc.docstatus != 0:
                continue
            doc.flags.ignore_permissions = True
            frappe.flags.ignore_account_permission = True
            doc.submit()
            frappe.db.commit()
        except Exception as e:
            frappe.db.rollback()
            still_stuck.append(f"{r['name']}: {type(e).__name__}: {e!s}"[:200])

    if still_stuck:
        users = []
        for role in RETRY_NOTIFY_ROLES:
            users.extend(frappe.get_all(
                "Has Role", filters={"role": role, "parenttype": "User"},
                pluck="parent",
            ))
        users = [u for u in set(users) if u not in ("Administrator", "Guest")]
        body = (
            f"POS Hardening: {len(still_stuck)} invoice(s) still stuck after "
            f"auto-retry.\n\n" + "\n".join(f"- {s}" for s in still_stuck[:10])
        )
        for u in users:
            frappe.publish_realtime(
                event="msgprint",
                message={"title": "POS Stuck Invoices", "message": body,
                         "indicator": "red"},
                user=u,
            )


def sle_health_check() -> None:
    """Weekly -- log SLE row count + growth, alert if growth >50K/week.

    Doesn't consolidate (Frappe v15 has built-in periodic stock reconciliation
    via Repost Item Valuation). This task surfaces growth so we know when
    to enable the heavier weekly Repost.
    """
    total = frappe.db.count("Stock Ledger Entry")
    last_7d = frappe.db.sql("""
        select count(*) from `tabStock Ledger Entry`
        where posting_date > DATE_SUB(CURDATE(), INTERVAL 7 DAY)
    """)[0][0]
    frappe.log_error(
        title="POS Hardening: weekly SLE health",
        message=f"Total SLE rows: {total:,}  |  Last 7 days: {last_7d:,}",
    )
    if last_7d > 50000:
        for role in ["Accounts Manager"]:
            users = frappe.get_all(
                "Has Role", filters={"role": role, "parenttype": "User"},
                pluck="parent",
            )
            for u in users:
                if u in ("Administrator", "Guest"):
                    continue
                frappe.publish_realtime(
                    event="msgprint",
                    message={
                        "title": "POS Hardening: high SLE growth",
                        "message": (f"{last_7d:,} new SLE rows in the last "
                                    f"7 days. Enable Repost Item Valuation if "
                                    f"Stock Balance reports slow down."),
                        "indicator": "orange",
                    },
                    user=u,
                )
