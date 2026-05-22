"""
Phase 6 / Step 5: 3 ERPNext Workflows for HR + Finance.

Workflows:
  1. Leave Application:
     Draft -> Line Manager -> HR Manager -> Approved
                 |              |
                 v              v
              Rejected      Rejected
     (Line Manager = branch Plant Manager for outlet staff;
      = Employee.reports_to for HQ staff. Resolved via approver assignment.)

  2. Expense Claim (tiered by sanctioned_amount):
     - <= 20,000:        Draft -> Line Manager -> Approved
     - 20,001 - 200,000: Draft -> Line Manager -> Head of Finance -> Approved
     - > 200,000:        Draft -> Line Manager -> Head of Finance -> COO -> Approved

  3. Payroll Entry (separation of duties):
     Draft -> HR Manager -> Internal Control -> COO -> Approved -> Submit

Email notifications: enabled for both submitter + next approver on every transition.

Run:
    curl -fsSL "<raw url>/scripts/step5_workflows.py" -o /tmp/s5.py
    bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/s5.py').read())"
"""

from __future__ import annotations
from pathlib import Path
import frappe


DRY_RUN = False


# ---------- Workflow State Catalogue ----------
WORKFLOW_STATES = [
    # (state, doc_status, style)
    ("Draft", 0, "Warning"),
    ("Line Manager Review", 0, "Warning"),
    ("HR Manager Review", 0, "Warning"),
    ("Internal Control Review", 0, "Warning"),
    ("Head of Finance Review", 0, "Warning"),
    ("COO Review", 0, "Warning"),
    ("Approved", 1, "Success"),
    ("Rejected", 0, "Danger"),
]


def ensure_workflow_states(report: list[str]) -> None:
    report.append("## 1. Workflow States")
    report.append("")
    for state_name, doc_status, style in WORKFLOW_STATES:
        if frappe.db.exists("Workflow State", state_name):
            report.append(f"  = `{state_name}` exists")
            continue
        if DRY_RUN:
            report.append(f"  + would-create state `{state_name}` (status={doc_status}, style={style})")
            continue
        frappe.get_doc({
            "doctype": "Workflow State",
            "workflow_state_name": state_name,
            "style": style,
        }).insert(ignore_permissions=True, ignore_if_duplicate=True)
        report.append(f"  + created state `{state_name}`")
    report.append("")


# ---------- Workflow Action Catalogue ----------
WORKFLOW_ACTIONS = [
    "Submit for Approval",
    "Approve",
    "Reject",
    "Forward to HR",
    "Forward to Head of Finance",
    "Forward to Internal Control",
    "Forward to COO",
]


def ensure_workflow_actions(report: list[str]) -> None:
    report.append("## 2. Workflow Actions")
    report.append("")
    for action_name in WORKFLOW_ACTIONS:
        if frappe.db.exists("Workflow Action Master", action_name):
            report.append(f"  = `{action_name}` exists")
            continue
        if DRY_RUN:
            report.append(f"  + would-create action `{action_name}`")
            continue
        frappe.get_doc({
            "doctype": "Workflow Action Master",
            "workflow_action_name": action_name,
        }).insert(ignore_permissions=True, ignore_if_duplicate=True)
        report.append(f"  + created action `{action_name}`")
    report.append("")


# ---------- Helper: ensure required Roles exist ----------
def ensure_role(name: str) -> None:
    if not frappe.db.exists("Role", name):
        frappe.get_doc({"doctype": "Role", "role_name": name, "desk_access": 1}).insert(ignore_permissions=True)


def ensure_required_roles(report: list[str]) -> None:
    report.append("## 3. Required Roles")
    report.append("")
    needed = ["Employee", "Leave Approver", "Expense Approver", "HR Manager",
              "Head of Finance", "Internal Control", "COO", "System Manager"]
    for r in needed:
        if frappe.db.exists("Role", r):
            report.append(f"  = role `{r}` exists")
        else:
            if DRY_RUN:
                report.append(f"  + would-create role `{r}`")
            else:
                ensure_role(r)
                report.append(f"  + created role `{r}`")
    report.append("")


# ---------- Workflow definitions ----------

def upsert_workflow(name: str, doctype: str, state_field: str, states: list[dict],
                    transitions: list[dict], report: list[str]) -> None:
    report.append(f"### Workflow: `{name}` on `{doctype}`")
    if frappe.db.exists("Workflow", name):
        if DRY_RUN:
            report.append("  = exists -- would-update transitions/states (skipping in DRY_RUN)")
            report.append("")
            return
        # Replace cleanly
        existing = frappe.get_doc("Workflow", name)
        existing.delete(ignore_permissions=True)
        report.append("  ~ removed existing for rebuild")
    if DRY_RUN:
        report.append(f"  + would-create with {len(states)} states, {len(transitions)} transitions")
        report.append("")
        return
    doc = frappe.get_doc({
        "doctype": "Workflow",
        "workflow_name": name,
        "document_type": doctype,
        "workflow_state_field": state_field,
        "is_active": 1,
        "send_email_alert": 1,
        "states": states,
        "transitions": transitions,
    })
    doc.insert(ignore_permissions=True)
    report.append(f"  + created with {len(states)} states, {len(transitions)} transitions")
    report.append("")


# ---------- Add custom workflow_state field if missing ----------
def ensure_workflow_state_field(doctype: str, fieldname: str, report: list[str]) -> None:
    cf = f"{doctype}-{fieldname}"
    if frappe.db.exists("Custom Field", cf):
        report.append(f"  = custom field `{cf}` exists")
        return
    if DRY_RUN:
        report.append(f"  + would-add custom workflow_state field on `{doctype}`")
        return
    frappe.get_doc({
        "doctype": "Custom Field",
        "dt": doctype,
        "fieldname": fieldname,
        "label": "Workflow State",
        "fieldtype": "Link",
        "options": "Workflow State",
        "read_only": 1,
        "in_list_view": 1,
        "no_copy": 1,
        "print_hide": 1,
        "insert_after": "amended_from",
    }).insert(ignore_permissions=True, ignore_if_duplicate=True)
    report.append(f"  + added `{cf}` (read-only, list view)")


# ---------- Workflow 1: Leave Application ----------
def build_leave_workflow(report: list[str]) -> None:
    report.append("## 4. Workflow: Leave Application")
    report.append("")
    ensure_workflow_state_field("Leave Application", "workflow_state", report)
    states = [
        {"state": "Draft", "doc_status": 0, "allow_edit": "Employee"},
        {"state": "Line Manager Review", "doc_status": 0, "allow_edit": "Leave Approver"},
        {"state": "HR Manager Review", "doc_status": 0, "allow_edit": "HR Manager"},
        {"state": "Approved", "doc_status": 1, "allow_edit": "HR Manager"},
        {"state": "Rejected", "doc_status": 0, "allow_edit": "HR Manager"},
    ]
    transitions = [
        {"state": "Draft", "action": "Submit for Approval", "next_state": "Line Manager Review", "allowed": "Employee"},
        {"state": "Line Manager Review", "action": "Forward to HR", "next_state": "HR Manager Review", "allowed": "Leave Approver"},
        {"state": "Line Manager Review", "action": "Reject", "next_state": "Rejected", "allowed": "Leave Approver"},
        {"state": "HR Manager Review", "action": "Approve", "next_state": "Approved", "allowed": "HR Manager"},
        {"state": "HR Manager Review", "action": "Reject", "next_state": "Rejected", "allowed": "HR Manager"},
    ]
    upsert_workflow("Sungas Leave Approval", "Leave Application", "workflow_state", states, transitions, report)


# ---------- Workflow 2: Expense Claim ----------
def build_expense_workflow(report: list[str]) -> None:
    report.append("## 5. Workflow: Expense Claim (tiered by sanctioned amount)")
    report.append("")
    ensure_workflow_state_field("Expense Claim", "workflow_state", report)
    states = [
        {"state": "Draft", "doc_status": 0, "allow_edit": "Employee"},
        {"state": "Line Manager Review", "doc_status": 0, "allow_edit": "Expense Approver"},
        {"state": "Head of Finance Review", "doc_status": 0, "allow_edit": "Head of Finance"},
        {"state": "COO Review", "doc_status": 0, "allow_edit": "COO"},
        {"state": "Approved", "doc_status": 1, "allow_edit": "Head of Finance"},
        {"state": "Rejected", "doc_status": 0, "allow_edit": "Head of Finance"},
    ]
    # Conditions on `total_sanctioned_amount` (drives tiered approval)
    transitions = [
        {"state": "Draft", "action": "Submit for Approval", "next_state": "Line Manager Review", "allowed": "Employee"},
        # Line Manager: low-value -> Approved direct; mid/high -> escalate
        {"state": "Line Manager Review", "action": "Approve", "next_state": "Approved", "allowed": "Expense Approver",
         "condition": "doc.total_sanctioned_amount <= 20000"},
        {"state": "Line Manager Review", "action": "Forward to Head of Finance", "next_state": "Head of Finance Review",
         "allowed": "Expense Approver", "condition": "doc.total_sanctioned_amount > 20000"},
        {"state": "Line Manager Review", "action": "Reject", "next_state": "Rejected", "allowed": "Expense Approver"},
        # HoF: mid -> Approved; high -> escalate to COO
        {"state": "Head of Finance Review", "action": "Approve", "next_state": "Approved", "allowed": "Head of Finance",
         "condition": "doc.total_sanctioned_amount <= 200000"},
        {"state": "Head of Finance Review", "action": "Forward to COO", "next_state": "COO Review",
         "allowed": "Head of Finance", "condition": "doc.total_sanctioned_amount > 200000"},
        {"state": "Head of Finance Review", "action": "Reject", "next_state": "Rejected", "allowed": "Head of Finance"},
        # COO: final
        {"state": "COO Review", "action": "Approve", "next_state": "Approved", "allowed": "COO"},
        {"state": "COO Review", "action": "Reject", "next_state": "Rejected", "allowed": "COO"},
    ]
    upsert_workflow("Sungas Expense Claim Approval", "Expense Claim", "workflow_state", states, transitions, report)


# ---------- Workflow 3: Payroll Entry ----------
def build_payroll_workflow(report: list[str]) -> None:
    report.append("## 6. Workflow: Payroll Entry (HR Mgr -> Internal Control -> COO)")
    report.append("")
    ensure_workflow_state_field("Payroll Entry", "workflow_state", report)
    states = [
        {"state": "Draft", "doc_status": 0, "allow_edit": "HR Manager"},
        {"state": "Internal Control Review", "doc_status": 0, "allow_edit": "Internal Control"},
        {"state": "COO Review", "doc_status": 0, "allow_edit": "COO"},
        {"state": "Approved", "doc_status": 1, "allow_edit": "COO"},
        {"state": "Rejected", "doc_status": 0, "allow_edit": "HR Manager"},
    ]
    transitions = [
        {"state": "Draft", "action": "Forward to Internal Control", "next_state": "Internal Control Review", "allowed": "HR Manager"},
        {"state": "Internal Control Review", "action": "Forward to COO", "next_state": "COO Review", "allowed": "Internal Control"},
        {"state": "Internal Control Review", "action": "Reject", "next_state": "Rejected", "allowed": "Internal Control"},
        {"state": "COO Review", "action": "Approve", "next_state": "Approved", "allowed": "COO"},
        {"state": "COO Review", "action": "Reject", "next_state": "Rejected", "allowed": "COO"},
    ]
    upsert_workflow("Sungas Payroll Approval", "Payroll Entry", "workflow_state", states, transitions, report)


# ---------- Set leave_approver per employee (Plant Manager for outlets, reports_to for HQ) ----------
def assign_leave_approvers(report: list[str]) -> None:
    report.append("## 7. Assign leave_approver per Employee")
    report.append("")
    employees = frappe.get_all(
        "Employee",
        filters={"status": "Active"},
        fields=["name", "employee_name", "branch", "reports_to", "user_id", "designation"],
    )
    # Build {branch: plant_manager_user_email}
    plant_mgrs: dict[str, str] = {}
    for pm in frappe.get_all(
        "Employee",
        filters={"status": "Active",
                 "designation": ["in", ["Plant Manager", "A.g Plant Manager"]]},
        fields=["name", "branch", "user_id"],
    ):
        if pm.get("branch") and pm.get("user_id"):
            plant_mgrs[pm["branch"]] = pm["user_id"]

    set_count = 0
    skipped = 0
    no_approver = 0
    for emp in employees:
        branch = emp.get("branch") or ""
        # Outlet staff -> Plant Manager of that branch
        approver = None
        if branch.lower() != "headquarters" and branch in plant_mgrs:
            approver = plant_mgrs[branch]
        # Plant Managers themselves report up to Operations Manager (HQ); use reports_to
        if not approver and emp.get("reports_to"):
            rep_user = frappe.db.get_value("Employee", emp["reports_to"], "user_id")
            if rep_user:
                approver = rep_user
        if not approver:
            no_approver += 1
            continue
        current = frappe.db.get_value("Employee", emp["name"], "leave_approver")
        if current == approver:
            skipped += 1
            continue
        if DRY_RUN:
            set_count += 1
            continue
        frappe.db.set_value("Employee", emp["name"], "leave_approver", approver)
        # Same person also handles expense claim
        if frappe.get_meta("Employee").has_field("expense_approver"):
            frappe.db.set_value("Employee", emp["name"], "expense_approver", approver)
        set_count += 1

    report.append(f"  Plant Managers found: {len(plant_mgrs)} (each owns a branch)")
    report.append(f"  Approver {'projected' if DRY_RUN else 'updated'}: {set_count}")
    report.append(f"  No change:               {skipped}")
    report.append(f"  No approver resolvable:  {no_approver}")
    if no_approver:
        report.append("  (Action: HR sets reports_to manually for these employees)")
    report.append("")


# ---------- Driver ----------
def main():
    print("=" * 72)
    print(f" Phase 6 / Step 5 -- Workflows (DRY_RUN={DRY_RUN})")
    print("=" * 72)

    report: list[str] = []
    report.append("# Step 5 -- Workflows: Leave + Expense Claim + Payroll Entry")
    report.append("")
    report.append(f"_Generated: {frappe.utils.now_datetime()} | Site: {frappe.local.site} | DRY_RUN={DRY_RUN}_")
    report.append("")

    ensure_workflow_states(report)
    ensure_workflow_actions(report)
    ensure_required_roles(report)
    build_leave_workflow(report)
    build_expense_workflow(report)
    build_payroll_workflow(report)
    assign_leave_approvers(report)

    if not DRY_RUN:
        frappe.db.commit()

    p = Path("/tmp/step5_workflows.md")
    p.write_text("\n".join(report), encoding="utf-8")
    print(f"\n[OK] wrote {p}\n")
    for line in report:
        print(line)


try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
