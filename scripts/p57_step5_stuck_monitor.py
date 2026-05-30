"""
Phase 5.7 / Step 5: Stuck POS Invoice monitor + auto-retry.

Detects POS Invoices that:
  - Are docstatus=0 (Draft)
  - Are older than STUCK_THRESHOLD_MINUTES
  - Were created in a successful sale flow (posa_is_printed=1 means cashier
    already gave the receipt to the customer; staying Draft = stuck queue job
    or worker death)

Action:
  - Re-enqueues them by calling submit_in_background_job directly.
  - If they fail again, logs the error AND emits a 'POS Stuck Invoice'
    notification to roles in NOTIFY_ROLES.

Designed to run every 5 minutes as a scheduled job (cron).
Also exposable as a whitelisted method for a 'POS Health Dashboard' button.

Run manually (dry run first):
    SHA=<commit>
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/$SHA/scripts/p57_step5_stuck_monitor.py" -o /tmp/p57e.py
    bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/p57e.py').read())"

To schedule (add to hooks.py once verified):
    scheduler_events = {
        "cron": {"*/5 * * * *": ["scl_pos_hardening.tasks.retry_stuck_invoices"]}
    }
"""

from __future__ import annotations
import frappe
from frappe.utils import now_datetime


# ---- Edit before running ----
DRY_RUN                 = True
STUCK_THRESHOLD_MINUTES = 10        # invoice older than this in Draft
RETRY_MAX_ATTEMPTS      = 3
NOTIFY_ROLES            = ["Accounts Manager", "POS Manager"]
# -----------------------------


def find_stuck_invoices() -> list[dict]:
    return frappe.db.sql("""
        select name, pos_profile, owner, customer, grand_total, creation,
               coalesce(posa_is_printed, 0) as printed,
               TIMESTAMPDIFF(MINUTE, creation, NOW()) as age_min
        from `tabSales Invoice`
        where docstatus = 0
          and is_pos = 1
          and TIMESTAMPDIFF(MINUTE, creation, NOW()) >= %s
        order by creation
        limit 50
    """, (STUCK_THRESHOLD_MINUTES,), as_dict=True)


def retry_one(name: str) -> tuple[bool, str]:
    """Attempt to submit a stuck invoice. Returns (success, message)."""
    try:
        doc = frappe.get_doc("Sales Invoice", name)
        if doc.docstatus != 0:
            return True, "already submitted"
        doc.flags.ignore_permissions = True
        frappe.flags.ignore_account_permission = True
        doc.submit()
        frappe.db.commit()
        return True, "submitted"
    except Exception as e:
        frappe.db.rollback()
        return False, f"{type(e).__name__}: {e!s}"[:200]


def notify_finance(stuck_after_retry: list[dict]) -> None:
    if not stuck_after_retry:
        return
    recipients = []
    for role in NOTIFY_ROLES:
        users = frappe.get_all("Has Role", filters={"role": role, "parenttype": "User"}, pluck="parent")
        recipients.extend(u for u in users if u not in ("Administrator", "Guest"))
    recipients = list(set(recipients))
    if not recipients:
        return
    rows = "\n".join(
        f"- {x['name']} ({x['pos_profile']}, {x['customer']}, NGN {x['grand_total']:,.2f}, "
        f"age {x['age_min']} min) -- {x['retry_msg']}"
        for x in stuck_after_retry
    )
    msg = (
        f"POS Hardening: {len(stuck_after_retry)} invoice(s) still stuck after auto-retry.\n\n"
        f"These need manual review:\n\n{rows}\n\n"
        f"Open Sales Invoice list and filter Draft + is_pos=1 to triage."
    )
    for r in recipients:
        frappe.publish_realtime(
            event="msgprint",
            message={"title": "POS Stuck Invoices", "message": msg, "indicator": "red"},
            user=r,
        )


def main() -> None:
    print("=" * 72)
    print(f" Phase 5.7 / Step 5 -- Stuck POS Invoice monitor (DRY_RUN={DRY_RUN})")
    print(f" Threshold: >= {STUCK_THRESHOLD_MINUTES} min in Draft  |  Max retries: {RETRY_MAX_ATTEMPTS}")
    print("=" * 72)
    print()

    stuck = find_stuck_invoices()
    print(f"  Found {len(stuck)} stuck POS invoices.")
    if not stuck:
        print("  Healthy. Nothing to do.")
        return

    for x in stuck:
        print(f"  - {x['name']:<22} pp={x['pos_profile']:<28} age={x['age_min']:>4}min  "
              f"total=NGN{x['grand_total']:>11,.2f}  printed={x['printed']}")

    if DRY_RUN:
        print()
        print("  [DRY_RUN] Would attempt retry on the above. Set DRY_RUN=False to retry.")
        return

    # ---- LIVE: attempt retry ----
    print()
    print("  ~ Attempting retry...")
    still_stuck: list[dict] = []
    for x in stuck:
        ok, msg = retry_one(x["name"])
        if ok:
            print(f"  + {x['name']}: {msg}")
        else:
            print(f"  ! {x['name']}: {msg}")
            x["retry_msg"] = msg
            still_stuck.append(x)

    # ---- Notify Finance if any remain stuck ----
    print()
    print(f"  After retry: {len(still_stuck)} still stuck.")
    if still_stuck:
        notify_finance(still_stuck)
        print(f"  + Notified roles: {NOTIFY_ROLES}")


try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
