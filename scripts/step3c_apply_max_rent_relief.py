"""
Phase 6 / Step 3c: Apply MAXIMUM rent relief to every active Employee.

Sungas 2026 policy: every active employee is deemed to claim the maximum
PAYE rent relief based on their declarations. The live PAYE Salary Component
formula (step3_paye_ntaa2025.py) reads `Employee.rent_paid_annually` and
applies `min(0.20 * rent, 500,000)`. By floor-setting that field to
2,500,000 (= 500,000 / 0.20) on every active employee, the relief always
caps at NGN 500,000 -- the maximum.

Idempotent: only employees whose current value is below the floor are touched.
Service providers (excluded from staff benefits in Step 4) are skipped.

DRY_RUN=True   -> print a list of who would be updated; no DB changes.
DRY_RUN=False  -> persist the values + commit.

Run:
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/feat/sungas-customizations/scripts/step3c_apply_max_rent_relief.py" -o /tmp/s3c.py
    bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/s3c.py').read())"
"""

from __future__ import annotations
from pathlib import Path
import frappe


DRY_RUN = True

RENT_RELIEF_FLOOR = 2_500_000  # NGN -- 20% of this = 500,000 (the statutory cap)

# Designations explicitly excluded from PAYE (also excluded here for cleanliness)
EXCLUDED_DESIGNATIONS = {
    "Non-Executive Director",
    "Chairman",
    "Independent Director",
}

# Service-provider designations that Step 4 already excluded from staff benefits.
SERVICE_PROVIDER_DESIGNATIONS = {
    "Vigilante",
    "Security Coordinator",
    "Freelance",
    "Freelancer",
}


def main():
    print("=" * 72)
    print(f" Phase 6 / Step 3c -- Max Rent Relief (DRY_RUN={DRY_RUN})")
    print(f" Floor: NGN {RENT_RELIEF_FLOOR:,.0f}  =>  PAYE relief = NGN 500,000 (cap)")
    print("=" * 72)

    rows = frappe.get_all(
        "Employee",
        filters={"status": "Active"},
        fields=["name", "employee_name", "designation", "rent_paid_annually"],
    )
    if not rows:
        print("  ! No active employees found")
        return

    to_update: list[dict] = []
    skipped_excluded = 0
    skipped_service = 0
    already_ok = 0

    for r in rows:
        des = (r.get("designation") or "").strip()
        if des in EXCLUDED_DESIGNATIONS:
            skipped_excluded += 1
            continue
        if des in SERVICE_PROVIDER_DESIGNATIONS:
            skipped_service += 1
            continue
        current = float(r.get("rent_paid_annually") or 0)
        if current >= RENT_RELIEF_FLOOR:
            already_ok += 1
            continue
        to_update.append({
            "name": r["name"],
            "employee_name": r["employee_name"],
            "designation": des,
            "current": current,
            "new": float(RENT_RELIEF_FLOOR),
        })

    print()
    print(f"  Active employees scanned   : {len(rows)}")
    print(f"  Excluded (PAYE-exempt roles): {skipped_excluded}")
    print(f"  Excluded (service providers): {skipped_service}")
    print(f"  Already at/above floor      : {already_ok}")
    print(f"  Need update                : {len(to_update)}")
    print()

    if to_update[:10]:
        print("  Preview (first 10):")
        for u in to_update[:10]:
            print(f"    - {u['name']:>14}  {u['employee_name'][:32]:<32}  "
                  f"{u['current']:>12,.0f} -> {u['new']:>12,.0f}")
        print()

    if DRY_RUN:
        print("[DRY_RUN] No changes written. Set DRY_RUN=False and re-run to apply.")
    else:
        for u in to_update:
            frappe.db.set_value("Employee", u["name"], "rent_paid_annually", u["new"])
        frappe.db.commit()
        print(f"[OK] Updated rent_paid_annually on {len(to_update)} employees.")
        print("     Live PAYE formula will now apply the NGN 500,000 cap for every")
        print("     non-excluded active employee in the next Salary Slip run.")

    # Markdown report
    p = Path("/tmp/step3c_max_rent_relief.md")
    md = [
        f"# Step 3c -- Max Rent Relief (DRY_RUN={DRY_RUN})",
        "",
        f"_Generated: {frappe.utils.now_datetime()} | Site: {frappe.local.site}_",
        "",
        f"- Floor applied        : NGN {RENT_RELIEF_FLOOR:,.0f}",
        "- Effective relief cap : NGN 500,000",
        f"- Active employees     : {len(rows)}",
        f"- PAYE-exempt roles skipped : {skipped_excluded}",
        f"- Service providers skipped : {skipped_service}",
        f"- Already at/above floor    : {already_ok}",
        f"- Updated                   : {len(to_update)}",
        "",
    ]
    if to_update:
        md.append("## Updated employees")
        md.append("")
        md.append("| Employee | Name | Designation | Was | Now |")
        md.append("|----------|------|-------------|----:|----:|")
        for u in to_update:
            md.append(f"| {u['name']} | {u['employee_name']} | {u['designation']} | "
                      f"{u['current']:,.0f} | {u['new']:,.0f} |")
    p.write_text("\n".join(md), encoding="utf-8")
    print(f"\n[OK] {p}")


try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
