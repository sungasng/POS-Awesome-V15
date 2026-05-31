"""Link Peace's User account to her Employee record."""
from pathlib import Path
import os
import frappe

EMP = "HR-EMP-00053"
USER = "peace.effiong@sungas.org"


def main():
    live = os.environ.get("LIVE", "0") == "1"
    L = []
    p = L.append
    p(f"# Link User `{USER}` -> Employee `{EMP}`")
    p(f"- Mode: {'LIVE' if live else 'DRY-RUN'}")
    p("")

    if not frappe.db.exists("Employee", EMP):
        p(f"- :x: `{EMP}` not found")
        _save(L)
        return

    cur = frappe.db.get_value("Employee", EMP,
                              ["employee_name", "user_id", "company_email"],
                              as_dict=True)
    p(f"- current: employee_name=`{cur['employee_name']}` "
      f"user_id=`{cur['user_id']}` company_email=`{cur['company_email']}`")

    if cur["user_id"] == USER:
        p("- :information_source: already linked.")
        _save(L)
        return

    if not live:
        p(f"- WOULD set user_id = `{USER}`")
        _save(L)
        return

    doc = frappe.get_doc("Employee", EMP)
    doc.user_id = USER
    # Also set company_email if missing -- helps notifications/audit trail
    if not doc.company_email:
        doc.company_email = USER
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    p(f"- :white_check_mark: linked. New user_id=`{doc.user_id}`")
    _save(L)


def _save(L):
    out = "\n".join(L)
    Path("/tmp/p57_link_peace.log").write_text(out, encoding="utf-8")
    print(out)


main()
