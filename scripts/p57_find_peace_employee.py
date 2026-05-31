"""Find Peace's Employee record (or auto-link)."""
from pathlib import Path
import frappe

EMAIL = "peace.effiong@sungas.org"


def main():
    L = []
    p = L.append
    p(f"# Find Employee for `{EMAIL}`")
    p("")

    # 1. Direct match on user_id
    rows = frappe.get_all(
        "Employee",
        filters={"user_id": EMAIL},
        fields=["name", "employee_name", "user_id", "status", "company"],
    )
    p(f"## 1. Employees with user_id = `{EMAIL}`: {len(rows)}")
    for r in rows:
        p(f"- `{r['name']}` -- {r['employee_name']} -- status={r['status']} -- company={r['company']}")
    p("")

    # 2. Fuzzy match on personal_email / company_email / employee_name
    fuzzy = frappe.db.sql("""
        select name, employee_name, user_id, personal_email, company_email, status
        from `tabEmployee`
        where personal_email = %s or company_email = %s
           or employee_name like %s
        limit 10
    """, (EMAIL, EMAIL, "%Peace%"), as_dict=True)
    p(f"## 2. Fuzzy match on Peace / emails: {len(fuzzy)}")
    for r in fuzzy:
        p(f"- `{r['name']}` -- {r['employee_name']}")
        p(f"    user_id=`{r['user_id']}` personal_email=`{r['personal_email']}` "
          f"company_email=`{r['company_email']}` status={r['status']}")
    p("")

    # 3. User account check
    u = frappe.db.exists("User", EMAIL)
    p(f"## 3. User record exists: {bool(u)}")
    if u:
        full = frappe.db.get_value("User", EMAIL, ["full_name", "enabled"], as_dict=True)
        p(f"- full_name=`{full['full_name']}` enabled={full['enabled']}")
    p("")

    out = "\n".join(L)
    Path("/tmp/p57_find_peace.log").write_text(out, encoding="utf-8")
    print(out)


main()
