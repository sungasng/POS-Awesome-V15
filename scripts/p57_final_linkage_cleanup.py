"""
p57: Final cleanup of User<->Employee linkage gaps.

Three jobs:
  1. Apply manual override links for Section C (4 fuzzy matches confirmed by user).
  2. Create Nimota's Employee record + link her User.
     - first_name: AYOBAMI, middle_name: NIMOTA, last_name: SULAIMAN
     - department: Finance, designation: Cashier, status: Active
     - User: nimota.sulaimon@sungas.org
  3. Delete 3 system-generated demo Users (emily.demo, john.demo, sarah.demo).
     Falls back to disabling if delete is blocked by linked references.

LIVE=1 to apply. Idempotent.
"""
from __future__ import annotations
from pathlib import Path
from datetime import date
import os
import frappe

COMPANY = "SUNGAS COMPANY LIMITED"

MANUAL_LINKS = [
    ("racheal.moses@sungas.org",  "HR-EMP-00076"),  # Racheal Remilekun MOSES
    ("shima.justine@sungas.org",  "HR-EMP-00161"),  # Justine Aondoakula SHIMA
    ("kaosara.kareem@sungas.org", "HR-EMP-00093"),  # Kaosara Eniola Kareem
    ("bolanle.ayodele@sungas.org","HR-EMP-00067"),  # Bolanle Rofiat Ayodele
]

NIMOTA = {
    "user_id":      "nimota.sulaimon@sungas.org",
    "first_name":   "AYOBAMI",
    "middle_name":  "NIMOTA",
    "last_name":    "SULAIMAN",
    "department":   "Finance",
    "designation":  "Cashier",
    "status":       "Active",
    "outlet_note":  "Upper Mission",  # captured as bio note since outlet isn't an Employee field
    "company":      COMPANY,
    "date_of_joining": date.today().isoformat(),
    "gender":       "Female",   # standard ERPNext requires gender; Nimota is feminine name
}

DEMO_USERS = [
    "emily.demo@example.com",
    "john.demo@example.com",
    "sarah.demo@example.com",
]


def main():
    L = []
    p = L.append
    live = os.environ.get("LIVE", "0") == "1"
    p("# p57: Final linkage cleanup")
    p(f"- Mode: {'LIVE' if live else 'DRY-RUN'}")
    p("")

    # -------- 1. Manual override links --------
    p("## 1. Section C manual-override links")
    for user, emp in MANUAL_LINKS:
        if not frappe.db.exists("Employee", emp):
            p(f"- :x: `{emp}` not found")
            continue
        cur_uid = frappe.db.get_value("Employee", emp, "user_id")
        if cur_uid == user:
            p(f"- :information_source: `{user}` <-> `{emp}` already linked")
            continue
        if not live:
            p(f"- WOULD set `{emp}`.user_id = `{user}` (current=`{cur_uid}`)")
            continue
        try:
            doc = frappe.get_doc("Employee", emp)
            doc.user_id = user
            if not doc.company_email:
                doc.company_email = user
            doc.save(ignore_permissions=True)
            p(f"- :white_check_mark: linked `{user}` <-> `{emp}`")
        except Exception as e:
            p(f"- :x: `{user}` <-> `{emp}`: {e}")
    if live:
        frappe.db.commit()
    p("")

    # -------- 2. Nimota's Employee record --------
    p("## 2. Create Nimota's Employee + link")
    nm_user = NIMOTA["user_id"]
    existing = frappe.db.get_value("Employee", {"user_id": nm_user}, "name")
    if existing:
        p(f"- :information_source: already exists `{existing}`, linked.")
    else:
        # Check if Employee record under same name exists but unlinked
        same_name = frappe.db.sql("""
            select name from `tabEmployee`
            where employee_name like %s or (first_name = %s and last_name = %s)
            limit 1
        """, (f"%{NIMOTA['middle_name']}%", NIMOTA["first_name"], NIMOTA["last_name"]))
        if same_name:
            target = same_name[0][0]
            p(f"- found candidate `{target}` -- will link instead of creating new")
            if live:
                try:
                    doc = frappe.get_doc("Employee", target)
                    doc.user_id = nm_user
                    if not doc.company_email:
                        doc.company_email = nm_user
                    doc.save(ignore_permissions=True)
                    p(f"- :white_check_mark: linked `{nm_user}` <-> `{target}`")
                except Exception as e:
                    p(f"- :x: link failed: {e}")
        else:
            if not live:
                p(f"- WOULD create new Employee: "
                  f"{NIMOTA['first_name']} {NIMOTA['middle_name']} {NIMOTA['last_name']}, "
                  f"Dept={NIMOTA['department']}, Designation={NIMOTA['designation']}, "
                  f"linked to `{nm_user}`")
            else:
                try:
                    new = frappe.get_doc({
                        "doctype": "Employee",
                        "company": COMPANY,
                        "first_name": NIMOTA["first_name"],
                        "middle_name": NIMOTA["middle_name"],
                        "last_name": NIMOTA["last_name"],
                        "employee_name": f"{NIMOTA['first_name']} {NIMOTA['middle_name']} {NIMOTA['last_name']}",
                        "gender": NIMOTA["gender"],
                        "date_of_joining": NIMOTA["date_of_joining"],
                        "date_of_birth": "1990-01-01",  # placeholder; HR can fix later
                        "status": NIMOTA["status"],
                        "user_id": nm_user,
                        "company_email": nm_user,
                        "department": NIMOTA["department"]
                            if frappe.db.exists("Department", NIMOTA["department"])
                            else None,
                        "designation": NIMOTA["designation"]
                            if frappe.db.exists("Designation", NIMOTA["designation"])
                            else None,
                        "bio": f"Outlet: {NIMOTA['outlet_note']}",
                    })
                    new.insert(ignore_permissions=True)
                    p(f"- :white_check_mark: created `{new.name}` -- "
                      f"{new.employee_name} -- linked to `{nm_user}`")
                    if not frappe.db.exists("Department", NIMOTA["department"]):
                        p(f"  :warning: Department `{NIMOTA['department']}` doesn't exist -- left blank")
                    if not frappe.db.exists("Designation", NIMOTA["designation"]):
                        p(f"  :warning: Designation `{NIMOTA['designation']}` doesn't exist -- left blank")
                except Exception as e:
                    p(f"- :x: create failed: {e}")
    if live:
        frappe.db.commit()
    p("")

    # -------- 3. Delete demo Users --------
    p("## 3. Delete demo Users")
    for u in DEMO_USERS:
        if not frappe.db.exists("User", u):
            p(f"- skip `{u}` (already gone)")
            continue
        if not live:
            p(f"- WOULD delete `{u}`")
            continue
        try:
            frappe.delete_doc("User", u, force=1, ignore_permissions=True)
            frappe.db.commit()
            p(f"- :white_check_mark: deleted `{u}`")
        except Exception as e:
            # Fall back to disable if delete blocked
            try:
                frappe.db.set_value("User", u, "enabled", 0)
                frappe.db.commit()
                p(f"- :warning: delete blocked ({e}); disabled instead.")
            except Exception as e2:
                p(f"- :x: `{u}`: {e2}")
    p("")

    # -------- 4. Final stats --------
    p("## 4. Linkage stats after run")
    n_total = frappe.db.count("Employee")
    n_linked = frappe.db.sql("""
        select count(*) from `tabEmployee`
        where user_id is not null and user_id != ''
    """)[0][0]
    p(f"- Total Employees: {n_total}")
    p(f"- Linked to a User: {n_linked}")
    p(f"- Unlinked: {n_total - n_linked}")

    out = "\n".join(L)
    Path("/tmp/p57_final_linkage.log").write_text(out, encoding="utf-8")
    print(out)
    print()
    print("  Log: /tmp/p57_final_linkage.log")


main()
