"""
p57: Inspect POSA-OS-26-0000003 close attempt outcome.

Checks:
  1. Current status / docstatus of POSA-OS-26-0000003
  2. Any POS Closing Shift records linked to it (any status)
  3. Most recent 5 POS Closing Shift records for POS - Ikeja (any status)
  4. POS Invoice Merge Log records for the period (consolidation tracker)
  5. Frappe queued / failed jobs touching this shift
  6. Error Log entries from the last 4 hours mentioning the shift name or
     Peace's email
  7. Comments / Version history on the Opening Shift

Read-only.
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime, timedelta
import frappe

SHIFT = "POSA-OS-26-0000003"
PROFILE = "POS - Ikeja"
USER = "peace.effiong@sungas.org"


def main():
    L = []
    p = L.append
    p(f"# Inspect close attempt for `{SHIFT}`"); p("")

    # 1) Current opening shift state
    p("## 1. POS Opening Shift current state")
    if not frappe.db.exists("POS Opening Shift", SHIFT):
        p(f"- :x: {SHIFT} does not exist"); _save(L); return
    os_doc = frappe.get_doc("POS Opening Shift", SHIFT)
    p(f"- name: {os_doc.name}")
    p(f"- status: **{os_doc.status}**")
    p(f"- docstatus: {os_doc.docstatus}  (0=draft, 1=submitted, 2=cancelled)")
    p(f"- period_start_date: {os_doc.period_start_date}")
    p(f"- pos_profile: {os_doc.pos_profile}")
    p(f"- user: {os_doc.user}")
    p(f"- modified: {os_doc.modified}")
    p("")

    # 2) Closing Shifts linked to this opening
    p("## 2. POS Closing Shift records that reference this Opening Shift")
    cs_links = frappe.db.sql("""
        select name, docstatus, status, period_end_date, posting_date,
               grand_total, modified, owner
        from `tabPOS Closing Shift`
        where pos_opening_shift = %s
        order by modified desc
    """, (SHIFT,), as_dict=True)
    if not cs_links:
        p("- (none) -- no Closing Shift document was ever created against this Opening")
    else:
        for r in cs_links:
            p(f"- {r['name']} | docstatus={r['docstatus']} status={r['status']} "
              f"period_end={r['period_end_date']} grand_total=NGN {float(r['grand_total'] or 0):,.2f} "
              f"modified={r['modified']} owner={r['owner']}")
    p("")

    # 3) Latest 5 closing shifts for the profile
    p("## 3. Last 5 POS Closing Shift records for `POS - Ikeja`")
    recent_cs = frappe.db.sql("""
        select name, docstatus, status, period_end_date, modified, pos_opening_shift
        from `tabPOS Closing Shift`
        where pos_profile = %s
        order by modified desc limit 5
    """, (PROFILE,), as_dict=True)
    if not recent_cs:
        p("- (none ever)")
    else:
        for r in recent_cs:
            p(f"- {r['name']} | docstatus={r['docstatus']} status={r['status']} "
              f"period_end={r['period_end_date']} modified={r['modified']} "
              f"linked_opening={r['pos_opening_shift']}")
    p("")

    # 4) POS Invoice Merge Log
    p("## 4. POS Invoice Merge Log records (consolidation tracker) -- last 5")
    pim = frappe.db.sql("""
        select name, docstatus, posting_date, pos_closing_entry, consolidated_invoice,
               creation, modified
        from `tabPOS Invoice Merge Log`
        order by creation desc limit 5
    """, as_dict=True)
    if not pim:
        p("- (none in system)")
    else:
        for r in pim:
            p(f"- {r['name']} | docstatus={r['docstatus']} posting_date={r['posting_date']} "
              f"pos_closing_entry={r['pos_closing_entry']} "
              f"consolidated_invoice={r['consolidated_invoice']} "
              f"creation={r['creation']}")
    p("")

    # 5) Recent error logs
    since = (datetime.utcnow() - timedelta(hours=6)).strftime("%Y-%m-%d %H:%M:%S")
    p(f"## 5. Error Log entries since {since} (UTC) mentioning shift / Peace")
    errs = frappe.db.sql("""
        select name, creation, method, error
        from `tabError Log`
        where creation >= %s
          and (error like %s or error like %s or error like %s or method like %s)
        order by creation desc limit 20
    """, (since, f"%{SHIFT}%", f"%{USER}%", "%pos_closing_shift%", "%pos_closing%"), as_dict=True)
    if not errs:
        p("- (no relevant error log entries)")
    else:
        for r in errs:
            snippet = (r['error'] or '')[:500].replace("\n", " ")
            p(f"- {r['creation']} | method={r['method']}")
            p(f"  - {snippet}...")
    p("")

    # 6) RQ Job queue (queued / failed jobs)
    p("## 6. RQ Job records (queued / failed) -- last 10")
    try:
        jobs = frappe.db.sql("""
            select name, status, method_name, creation, modified
            from `tabRQ Job`
            where creation >= %s
            order by creation desc limit 10
        """, (since,), as_dict=True)
        if not jobs:
            p("- (no recent RQ Jobs)")
        else:
            for j in jobs:
                p(f"- {j['name']} | status={j['status']} method={j['method_name']} "
                  f"creation={j['creation']}")
    except Exception as e:
        p(f"- (RQ Job table not queryable: {e})")
    p("")

    # 7) Comments / Versions on the opening shift
    p("## 7. Recent activity / comments on the Opening Shift")
    versions = frappe.db.sql("""
        select creation, owner, data
        from `tabVersion`
        where ref_doctype = 'POS Opening Shift' and docname = %s
        order by creation desc limit 5
    """, (SHIFT,), as_dict=True)
    if not versions:
        p("- (no Version history)")
    else:
        for v in versions:
            p(f"- {v['creation']} by {v['owner']}: {v['data'][:300]}...")
    comments = frappe.db.sql("""
        select creation, owner, content
        from `tabComment`
        where reference_doctype = 'POS Opening Shift' and reference_name = %s
        order by creation desc limit 5
    """, (SHIFT,), as_dict=True)
    if comments:
        p("Comments:")
        for c in comments:
            p(f"- {c['creation']} by {c['owner']}: {c['content']}")
    p("")

    # Summary
    p("## Hypothesis")
    if cs_links:
        sub = [r for r in cs_links if r["docstatus"] == 1]
        drafts = [r for r in cs_links if r["docstatus"] == 0]
        if sub:
            p(f"- A submitted Closing Shift exists ({sub[0]['name']}) but the Opening Shift")
            p(f"  status is `{os_doc.status}` (not 'Closed'). State inconsistency -- can be ")
            p(f"  fixed by re-syncing the Opening Shift status.")
        elif drafts:
            p(f"- A DRAFT Closing Shift exists ({drafts[0]['name']}) -- Peace's attempt landed")
            p(f"  here but was never submitted. Likely a silent error during submission.")
        else:
            cancelled = [r for r in cs_links if r["docstatus"] == 2]
            if cancelled:
                p(f"- The Closing Shift was created and then cancelled ({cancelled[0]['name']}).")
    else:
        p("- No Closing Shift was created at all. Peace's UI may have shown success but the")
        p("  submit call was rejected at the backend before any record was created. Check the")
        p("  Error Log section above for the actual reason.")
    p("")

    _save(L)


def _save(L):
    out = "\n".join(L)
    Path("/tmp/p57_inspect_close.log").write_text(out, encoding="utf-8")
    print(out)
    print()
    print(f"  Log: /tmp/p57_inspect_close.log")


main()
