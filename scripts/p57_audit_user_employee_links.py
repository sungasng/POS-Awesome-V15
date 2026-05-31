"""
p57: Audit + fix User <-> Employee linkage gaps.

Why this matters:
  GL account `2608 - Cash Suspense - Cashier Recovery - SCL` is type=Receivable,
  which requires Party Type + Party on every Journal Entry row. The Phase-2
  auto-posting hook (and the current backfill script) resolve Party=Employee
  via Employee.user_id == <session_user_email>. If user_id is NULL, the JE
  fails to post -- exactly what happened with Peace today.

What this does:
  WAVE=1 (read-only): scans all enabled Users in the system, finds:
    a) Users with NO Employee record at all
    b) Users with an Employee record but user_id NOT set
    c) Users where Employee.user_id mismatches User.name (different email)
    d) Multiple Employee records claiming the same User
  Proposes auto-link mappings via fuzzy match on company_email, personal_email,
  and (employee_name vs user.full_name) similarity.

  WAVE=2 (LIVE=1): applies the high-confidence auto-links.
                    Skips ambiguous cases (logs them for manual review).

Filtering:
    SCOPE_ROLE      Restrict to Users holding this Role (default empty = all).
                    Examples: "POS User", "Cashier", "Sales User".
    SCOPE_EMAIL_LIKE Restrict to user emails matching this LIKE pattern (default empty).
"""
from __future__ import annotations
from pathlib import Path
import os
import re
import frappe


SYSTEM_USERS = {"Administrator", "Guest", "admin@example.com"}


def _norm_name(s: str) -> str:
    """Normalise a name for fuzzy compare: lowercase, strip non-alphanum,
    sort tokens (so 'Ukeme Peace Effiong' == 'Peace Effiong Ukeme')."""
    if not s:
        return ""
    tokens = re.findall(r"[a-zA-Z0-9]+", s.lower())
    return " ".join(sorted(tokens))


def _name_score(a: str, b: str) -> float:
    """Jaccard token overlap on normalised tokens."""
    sa = set(_norm_name(a).split())
    sb = set(_norm_name(b).split())
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def main():
    L = []
    p = L.append
    live = os.environ.get("LIVE", "0") == "1"
    wave = os.environ.get("WAVE", "1").strip()
    scope_role = os.environ.get("SCOPE_ROLE", "").strip()
    scope_like = os.environ.get("SCOPE_EMAIL_LIKE", "").strip()

    p("# p57: User <-> Employee linkage audit + fixup")
    p("")
    p(f"- Wave: {wave}    Mode: {'LIVE' if live else 'DRY-RUN'}")
    if scope_role:
        p(f"- SCOPE_ROLE: `{scope_role}`")
    if scope_like:
        p(f"- SCOPE_EMAIL_LIKE: `{scope_like}`")
    p("")

    # --- collect Users in scope ---
    user_filters = {"enabled": 1, "user_type": "System User"}
    users = frappe.get_all(
        "User",
        filters=user_filters,
        fields=["name", "full_name", "email"],
    )
    users = [u for u in users if u["name"] not in SYSTEM_USERS]
    if scope_like:
        users = [u for u in users if scope_like.lower() in u["name"].lower()]
    if scope_role:
        rolled = set(frappe.db.sql_list("""
            select distinct parent from `tabHas Role`
            where parenttype = 'User' and role = %s
        """, (scope_role,)))
        users = [u for u in users if u["name"] in rolled]

    p(f"## In-scope Users: **{len(users)}**")
    p("")

    # --- collect all Employees once ---
    emps = frappe.get_all(
        "Employee",
        fields=["name", "employee_name", "user_id", "company_email",
                "personal_email", "status"],
    )
    emp_by_userid = {e["user_id"]: e for e in emps if e["user_id"]}
    emp_by_compemail = {(e["company_email"] or "").lower(): e
                        for e in emps if e["company_email"]}
    emp_by_persemail = {(e["personal_email"] or "").lower(): e
                        for e in emps if e["personal_email"]}

    p(f"## Total Employee records: **{len(emps)}**  "
      f"linked (user_id set): {len(emp_by_userid)}  "
      f"unlinked: {len(emps) - len(emp_by_userid)}")
    p("")

    # --- classify each user ---
    ok = []         # already linked correctly
    auto_link = []  # confident auto-link candidate
    review = []     # ambiguous / manual review
    no_emp = []     # no Employee record at all

    for u in users:
        uname = u["name"]
        full = u.get("full_name") or ""
        # Already linked?
        emp = emp_by_userid.get(uname)
        if emp:
            ok.append((uname, emp["name"], emp["employee_name"]))
            continue
        # Try company_email match
        match = emp_by_compemail.get(uname.lower())
        if match and not match["user_id"]:
            auto_link.append((uname, match["name"], match["employee_name"],
                              "company_email exact", 1.0))
            continue
        # Try personal_email match
        match = emp_by_persemail.get(uname.lower())
        if match and not match["user_id"]:
            auto_link.append((uname, match["name"], match["employee_name"],
                              "personal_email exact", 1.0))
            continue
        # Fuzzy: name token overlap >= 0.66 and no other strong claim
        candidates = []
        for e in emps:
            if e["user_id"]:
                continue
            s = _name_score(full, e["employee_name"])
            if s >= 0.66:
                candidates.append((s, e))
        if len(candidates) == 1:
            s, e = candidates[0]
            label = "fuzzy-name unique"
            (auto_link if s >= 0.8 else review).append(
                (uname, e["name"], e["employee_name"], label, s)
            )
            continue
        if len(candidates) > 1:
            candidates.sort(key=lambda x: -x[0])
            top = candidates[0][1]
            review.append((uname, top["name"], top["employee_name"],
                           f"fuzzy-name top of {len(candidates)}",
                           candidates[0][0]))
            continue
        no_emp.append((uname, full))

    # --- report ---
    p("## A. Already linked (no action) — {} users".format(len(ok)))
    if ok:
        p("| User | Employee | Name |")
        p("|------|----------|------|")
        for u, e, n in ok:
            p(f"| `{u}` | `{e}` | {n} |")
    p("")

    p("## B. Auto-link candidates (HIGH confidence) — {} users".format(len(auto_link)))
    if auto_link:
        p("| User | Employee | Name | Match | Score |")
        p("|------|----------|------|-------|------:|")
        for u, e, n, label, s in auto_link:
            p(f"| `{u}` | `{e}` | {n} | {label} | {s:.2f} |")
    p("")

    p("## C. Manual review (ambiguous fuzzy) — {} users".format(len(review)))
    if review:
        p("| User | Top Employee | Name | Reason | Score |")
        p("|------|--------------|------|--------|------:|")
        for u, e, n, label, s in review:
            p(f"| `{u}` | `{e}` | {n} | {label} | {s:.2f} |")
    p("")

    p("## D. No Employee record found — {} users".format(len(no_emp)))
    if no_emp:
        p("| User | Full name |")
        p("|------|-----------|")
        for u, n in no_emp:
            p(f"| `{u}` | {n} |")
    p("")

    # --- WAVE 2 apply ---
    if wave == "2":
        p("## E. Applying auto-links")
        if not live:
            p("- DRY-RUN: would apply the {} auto-link(s) above".format(len(auto_link)))
        else:
            applied, failed = 0, []
            for u, emp_name, _, label, _ in auto_link:
                try:
                    doc = frappe.get_doc("Employee", emp_name)
                    if doc.user_id == u:
                        continue
                    doc.user_id = u
                    if not doc.company_email:
                        doc.company_email = u
                    doc.save(ignore_permissions=True)
                    applied += 1
                except Exception as e:
                    failed.append((u, emp_name, str(e)))
            frappe.db.commit()
            p(f"- :white_check_mark: applied: {applied}")
            if failed:
                p(f"- :x: failed: {len(failed)}")
                for u, e, err in failed:
                    p(f"  - `{u}` -> `{e}`: {err}")

    p("")
    p("---")
    p("## Summary")
    p(f"- Already linked:        **{len(ok)}**")
    p(f"- Will auto-link (WAVE 2): **{len(auto_link)}**")
    p(f"- Need manual review:    **{len(review)}**")
    p(f"- No Employee at all:    **{len(no_emp)}**")
    if review:
        p("")
        p("**For section C (manual review)**: tell the agent which User->Employee")
        p("mapping is correct; we'll add a manual override map and re-run WAVE 2.")
    if no_emp:
        p("")
        p("**For section D (no Employee)**: these users may be admin/IT/contractor")
        p("accounts that don't need cashier variance tracking. Confirm scope.")

    out = "\n".join(L)
    Path("/tmp/p57_link_audit.log").write_text(out, encoding="utf-8")
    print(out)
    print()
    print("  Log: /tmp/p57_link_audit.log")


main()
