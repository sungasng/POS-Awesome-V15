"""
Phase 6 — HRMS Step 1: Employee Data Audit (READ-ONLY).

Compares the 219-staff roster from April 2026 payroll vs the live Frappe
`Employee` master, and emits /tmp/employee_audit.md with a comprehensive
gap report.

Touches nothing — purely diagnostic.

Run:
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/feat/sungas-customizations/scripts/_payroll_roster.py" -o /tmp/_payroll_roster.py
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/feat/sungas-customizations/scripts/employee_audit.py"   -o /tmp/employee_audit.py
    bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/employee_audit.py').read())"

Output:
    /tmp/employee_audit.md  -- share back so we can move to Step 2.
"""

from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import frappe


# ---------------------------------------------------------------------------
# Load the roster from the sibling module dropped by the prior curl.
# ---------------------------------------------------------------------------
sys.path.insert(0, "/tmp")
try:
    from _payroll_roster import PAYROLL_APR_2026 as ROSTER  # type: ignore
except Exception as exc:
    raise SystemExit(
        f"[FATAL] could not import /tmp/_payroll_roster.py -- did you curl it? {exc}"
    )


# ---------------------------------------------------------------------------
# Name normalisation helpers (handles word-order swaps + case + punctuation).
# ---------------------------------------------------------------------------
def _tokenise(name: str) -> frozenset[str]:
    return frozenset(t for t in re.split(r"[^A-Za-z]+", name.upper()) if t)


def build_employee_index() -> dict:
    """{ token_set: [employee_doc_dict, ...] } over all live employees."""
    idx = defaultdict(list)
    desired = [
        "name", "employee_name", "status", "designation", "department",
        "branch", "company", "cost_center", "payroll_cost_center",
        "user_id", "date_of_joining", "salary_mode", "pan_number", "iban",
        "bank_name", "bank_ac_no", "pf_number", "gender",
    ]
    # Only request fields that actually exist on this site's Employee meta
    # (v15 dropped some, sites add some via custom fields).
    meta = frappe.get_meta("Employee")
    fields = [f for f in desired if f in {"name", "employee_name"} or meta.has_field(f)]
    for emp in frappe.get_all("Employee", filters={}, fields=fields):
        idx[_tokenise(emp["employee_name"] or "")].append(emp)
    return idx


def lookup_employee(payroll_name: str, idx: dict):
    tokens = _tokenise(payroll_name)
    # exact (order-independent)
    if tokens in idx:
        hits = idx[tokens]
        return hits[0] if len(hits) == 1 else ("ambiguous", hits)
    # subset / superset (e.g. payroll has middle name, ERP doesn't)
    candidates = [
        cand for key, cands in idx.items() for cand in cands
        if tokens and (tokens <= key or key <= tokens)
        and len(tokens & key) >= 2  # at least 2 matching tokens
    ]
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        return ("ambiguous", candidates)
    return None


# ---------------------------------------------------------------------------
# Position normalisation map -- groups FILLER / Filler / filler / FLLER etc.
# ---------------------------------------------------------------------------
def normalise_position(p: str) -> str:
    p = p.strip().upper()
    # collapse known typos
    p = p.replace("FLLER", "FILLER").replace("FLILLER", "FILLER")
    p = p.replace("PLATFORM SUP", "PLATFORM SUPERVISOR")
    p = p.replace("PLATFROM", "PLATFORM")
    return re.sub(r"\s+", " ", p)


# ---------------------------------------------------------------------------
# Report builder.
# ---------------------------------------------------------------------------
def build_report() -> str:
    idx = build_employee_index()
    total_emp_records = sum(len(v) for v in idx.values())

    matched: list[tuple[dict, dict]] = []        # (payroll_row, employee_doc)
    unmatched: list[dict] = []
    ambiguous: list[tuple[dict, list]] = []

    for row in ROSTER:
        hit = lookup_employee(row["name"], idx)
        if hit is None:
            unmatched.append(row)
        elif isinstance(hit, tuple) and hit[0] == "ambiguous":
            ambiguous.append((row, hit[1]))
        else:
            matched.append((row, hit))

    # position normalisation map
    canon_to_variants: dict[str, set[str]] = defaultdict(set)
    for row in ROSTER:
        canon_to_variants[normalise_position(row["position"])].add(row["position"])

    # gross-pay bands
    bands_def = [(0, 50_000), (50_000, 100_000), (100_000, 150_000),
                 (150_000, 250_000), (250_000, 500_000),
                 (500_000, 1_000_000), (1_000_000, 1e12)]
    band_counts = Counter()
    for row in ROSTER:
        for lo, hi in bands_def:
            if lo <= row["gross"] < hi:
                band_counts[(lo, hi)] += 1
                break

    # field-completeness sweep on matched rows (meta-aware -- skip non-existent fields)
    field_gaps = Counter()
    candidate_fields = ["designation", "department", "branch", "cost_center",
                        "payroll_cost_center", "user_id", "bank_name",
                        "bank_ac_no", "pf_number", "pan_number"]
    emp_meta = frappe.get_meta("Employee")
    field_to_check = [f for f in candidate_fields if emp_meta.has_field(f)]
    for _, emp in matched:
        for f in field_to_check:
            if not emp.get(f):
                field_gaps[f] += 1

    # employees in ERP NOT in April payroll (potential leavers or HRMS-only records)
    matched_emp_names = {e["name"] for _, e in matched}
    erp_not_in_payroll: list[dict] = []
    for cands in idx.values():
        for c in cands:
            if c["name"] not in matched_emp_names and c.get("status") == "Active":
                erp_not_in_payroll.append(c)

    # ----- compose markdown -----
    lines: list[str] = []
    lines.append("# Sungas — Employee Data Audit (Phase 6 / Step 1)")
    lines.append("")
    lines.append(f"_Generated: {frappe.utils.now_datetime()}_  ")
    lines.append(f"_Site: {frappe.local.site}_")
    lines.append("")

    lines.append("## 1. Headcount summary")
    lines.append("")
    lines.append(f"- **Payroll roster (April 2026)**: **{len(ROSTER)}** rows")
    lines.append(f"- **Frappe `Employee` master**: **{total_emp_records}** records ({sum(1 for cs in idx.values() for c in cs if c.get('status')=='Active')} Active)")
    lines.append("")
    lines.append("| Match status | Count |")
    lines.append("|---|---:|")
    lines.append(f"| ✅ Matched 1:1 | {len(matched)} |")
    lines.append(f"| ❌ In payroll, NOT in ERP | {len(unmatched)} |")
    lines.append(f"| ⚠️ Ambiguous (multiple ERP candidates) | {len(ambiguous)} |")
    lines.append(f"| 👻 Active in ERP, NOT in April payroll | {len(erp_not_in_payroll)} |")
    lines.append("")

    lines.append("## 2. Gross-pay distribution (payroll roster)")
    lines.append("")
    lines.append("| Band | Headcount |")
    lines.append("|---|---:|")
    for (lo, hi), n in sorted(band_counts.items()):
        lab = f"<₦{hi/1000:.0f}K" if lo == 0 else (f"≥₦{lo/1_000_000:.0f}M" if hi >= 1e9 else f"₦{lo/1000:.0f}K – ₦{hi/1000:.0f}K")
        lines.append(f"| {lab} | {n} |")
    lines.append("")

    lines.append("## 3. Field gaps in matched employees")
    lines.append("")
    lines.append("How many of the matched `Employee` records are missing each field:")
    lines.append("")
    lines.append("| Field | Missing count | % of matched |")
    lines.append("|---|---:|---:|")
    denom = max(1, len(matched))
    for f in field_to_check:
        lines.append(f"| `{f}` | {field_gaps[f]} | {field_gaps[f]/denom:.0%} |")
    lines.append("")

    lines.append("## 4. Position normalisation map")
    lines.append("")
    lines.append("Group every distinct payroll position string under one canonical Designation.")
    lines.append("(Order: most-used canonical first.)")
    lines.append("")
    lines.append("| Canonical | Variants seen | Headcount |")
    lines.append("|---|---|---:|")
    canon_counts = Counter(normalise_position(r["position"]) for r in ROSTER)
    for canon, _ in canon_counts.most_common():
        variants = sorted(canon_to_variants[canon])
        n = canon_counts[canon]
        lines.append(f"| `{canon}` | {' / '.join(repr(v) for v in variants)} | {n} |")
    lines.append("")

    lines.append("## 5. Unmatched — need new Employee records")
    lines.append("")
    if not unmatched:
        lines.append("_None._ 🎉")
    else:
        lines.append(f"**{len(unmatched)} payroll rows have no matching ERP `Employee`.**  ")
        lines.append("These need creation (or fuzzy-match tuning).")
        lines.append("")
        lines.append("| Outlet | Name | Position | Gross (₦) | Pay mode |")
        lines.append("|---|---|---|---:|---|")
        for r in sorted(unmatched, key=lambda x: (x["outlet"], x["name"])):
            lines.append(f"| {r['outlet']} | {r['name']} | {r['position']} | {r['gross']:,.0f} | {r['pay_mode']} |")
    lines.append("")

    lines.append("## 6. Ambiguous matches — need manual disambiguation")
    lines.append("")
    if not ambiguous:
        lines.append("_None._")
    else:
        for row, cands in ambiguous:
            lines.append(f"- **{row['name']}** ({row['outlet']}) -- ERP candidates: " +
                         ", ".join(f"`{c['name']}` ({c.get('designation') or '?'} @ {c.get('branch') or '?'})" for c in cands))
    lines.append("")

    lines.append("## 7. Active in ERP but not in April payroll (potential exits / stale records)")
    lines.append("")
    if not erp_not_in_payroll:
        lines.append("_None._")
    else:
        lines.append("| ERP Employee ID | Name | Designation | Branch | Status |")
        lines.append("|---|---|---|---|---|")
        for e in sorted(erp_not_in_payroll, key=lambda x: x.get("employee_name") or ""):
            lines.append(f"| {e['name']} | {e.get('employee_name')} | {e.get('designation') or ''} | {e.get('branch') or ''} | {e.get('status') or ''} |")
    lines.append("")

    lines.append("## 8. Recommendations for Step 2")
    lines.append("")
    lines.append("1. **Create / update missing Employee records** (Section 5) before Step 2 starts.")
    lines.append("2. **Apply position normalisation map** (Section 4) -> single canonical Designation list (target: ~25 rows).")
    lines.append("3. **Backfill missing fields** (Section 3) priority order: `branch`, `cost_center`, `bank_name/bank_ac_no`, `pan_number` (TIN), `pf_number` (PenCom PIN).")
    lines.append("4. **Resolve ambiguous matches** (Section 6) -- 1 line per person.")
    lines.append("5. **Reconcile exits/joiners** (Section 7) -- decide Active/Inactive/Left for each.")
    lines.append("")

    return "\n".join(lines)


def main():
    print("=" * 72)
    print(" Phase 6 / Step 1 -- Employee Data Audit (read-only)")
    print("=" * 72)
    md = build_report()
    out = Path("/tmp/employee_audit.md")
    out.write_text(md, encoding="utf-8")
    print(f"\n[OK] wrote {out} ({len(md):,} chars)")
    print("\n----- preview -----\n")
    # print first 60 lines so it's visible in bench shell
    for line in md.splitlines()[:60]:
        print(line)
    print("\n... (truncated, full file at /tmp/employee_audit.md) ...\n")


# bench execute's locals/globals scope-fix
try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
