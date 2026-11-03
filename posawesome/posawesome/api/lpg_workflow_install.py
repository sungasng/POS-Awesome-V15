"""
Idempotent installer for the LPG Price Change approval workflow.

Run via the `after_install` and `after_migrate` hooks. Creates:
    - Roles: LPG POS User, LPG Plant Manager, LPG Head of Sales, LPG Head of Finance
    - Workflow States: Pending Plant Manager, Pending Head of Sales,
                       Pending Head of Finance, Approved, Rejected
    - Workflow Actions: Approve, Reject
    - Workflow: "LPG Price Change Approval" on doctype "LPG Price Change Request"

Approval ladder:
    POS user (anyone) creates Draft -> Submit transitions to "Pending Plant Manager"
    Plant Manager  -> Approve -> "Pending Head of Sales"
    Head of Sales  -> Approve -> "Pending Head of Finance"
    Head of Finance-> Approve -> "Approved" (auto-creates/updates the price tier)
    Any approver  -> Reject  -> ""
"""

from __future__ import annotations

import frappe

ROLES = (
    "LPG POS User",
    "LPG Plant Manager",
    "LPG Head of Sales",
    "LPG Head of Finance",
)

STATES = [
    {"state": "Pending Plant Manager",  "doc_status": "0", "style": "Warning",   "update_field": None,                              "update_value": None},
    {"state": "Pending Head of Sales",  "doc_status": "0", "style": "Warning",   "update_field": None,                              "update_value": None},
    {"state": "Pending Head of Finance","doc_status": "0", "style": "Warning",   "update_field": None,                              "update_value": None},
    {"state": "Approved",               "doc_status": "1", "style": "Success",   "update_field": None,                              "update_value": None},
    {"state": "Rejected",               "doc_status": "1", "style": "Danger",    "update_field": None,                              "update_value": None},
]

ACTIONS = ("Approve", "Reject")

TRANSITIONS = [
    # state, action, next_state, allowed_role, allow_self_approval
    ("Pending Plant Manager",   "Approve", "Pending Head of Sales",   "LPG Plant Manager",   0),
    ("Pending Plant Manager",   "Reject",  "Rejected",                "LPG Plant Manager",   1),
    ("Pending Head of Sales",   "Approve", "Pending Head of Finance", "LPG Head of Sales",   0),
    ("Pending Head of Sales",   "Reject",  "Rejected",                "LPG Head of Sales",   1),
    ("Pending Head of Finance", "Approve", "Approved",                "LPG Head of Finance", 0),
    ("Pending Head of Finance", "Reject",  "Rejected",                "LPG Head of Finance", 1),
]


def install_lpg_workflow():
    _ensure_roles()
    _ensure_states()
    _ensure_actions()
    _ensure_workflow()
    _ensure_pcr_originators()
    _ensure_bulk_upload_workflow()


def _ensure_roles():
    for role in ROLES:
        if not frappe.db.exists("Role", role):
            frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(
                ignore_permissions=True
            )


def _ensure_states():
    for s in STATES:
        if not frappe.db.exists("Workflow State", s["state"]):
            frappe.get_doc({
                "doctype": "Workflow State",
                "workflow_state_name": s["state"],
                "style": s["style"],
            }).insert(ignore_permissions=True)


def _ensure_actions():
    for a in ACTIONS:
        if not frappe.db.exists("Workflow Action Master", a):
            frappe.get_doc({
                "doctype": "Workflow Action Master",
                "workflow_action_name": a,
            }).insert(ignore_permissions=True)


def _ensure_workflow():
    name = "LPG Price Change Approval"
    if frappe.db.exists("Workflow", name):
        return  # Idempotent: don't overwrite manual tweaks

    wf = frappe.get_doc({
        "doctype": "Workflow",
        "workflow_name": name,
        "document_type": "LPG Price Change Request",
        "workflow_state_field": "workflow_state",
        "is_active": 1,
        "send_email_alert": 0,
        "states": [
            {
                "state": s["state"],
                "doc_status": s["doc_status"],
                "allow_edit": "LPG POS User" if "Pending Plant" in s["state"] else (
                    "LPG Plant Manager" if "Plant Manager" in s["state"]
                    else "LPG Head of Sales" if "Head of Sales" in s["state"]
                    else "LPG Head of Finance" if "Head of Finance" in s["state"]
                    else "System Manager"
                ),
            }
            for s in STATES
        ],
        "transitions": [
            {
                "state": t[0],
                "action": t[1],
                "next_state": t[2],
                "allowed": t[3],
                "allow_self_approval": t[4],
            }
            for t in TRANSITIONS
        ],
    })
    wf.insert(ignore_permissions=True)


# Patch 0017 -- BA Section 1.4: the Plant Team Lead (Plant Manager) originates a
# Plant-Level Override; Head Office Sales may originate as backup. Both must be
# able to save a request in its first state, alongside cashiers.
PCR_ORIGINATORS = ("LPG POS User", "LPG Plant Manager", "LPG Head of Sales")


def _ensure_pcr_originators():
    name = "LPG Price Change Approval"
    if not frappe.db.exists("Workflow", name):
        return
    wf = frappe.get_doc("Workflow", name)
    first = [s for s in wf.states if s.state == "Pending Plant Manager"]
    if not first:
        return
    have = {s.allow_edit for s in first}
    missing = [r for r in PCR_ORIGINATORS if r not in have]
    if not missing:
        return
    for role in missing:
        wf.append("states", {"state": "Pending Plant Manager", "doc_status": "0", "allow_edit": role})
    wf.save(ignore_permissions=True)


def _ensure_bulk_upload_workflow():
    """Pricing Wave B — P-3 Bulk Price Upload approval workflow.

    Single-step approval ladder (per user direction, 2026-02-20)::

        Draft
          └─(Submit, LPG Head of Sales)──▶ Pending Head of Finance
                                              ├─(Approve, LPG Head of Finance)──▶ Approved
                                              └─(Reject,  LPG Head of Finance)──▶ Rejected

    No CFO tier: any % change is HoF's call. The policy thresholds
    (`bulk_upload_change_flag_pct` / `bulk_upload_change_block_pct`) are
    still consulted by the doctype to mark rows + force a justification
    note, but neither triggers an extra approver.
    """
    name = "LPG Bulk Price Upload Approval"
    if frappe.db.exists("Workflow", name):
        return

    bulk_states = [
        {"state": "Draft",                  "doc_status": "0", "allow_edit": "LPG Head of Sales"},
        {"state": "Pending Head of Finance","doc_status": "0", "allow_edit": "LPG Head of Finance"},
        {"state": "Approved",               "doc_status": "1", "allow_edit": "System Manager"},
        {"state": "Rejected",               "doc_status": "1", "allow_edit": "System Manager"},
    ]

    # Defensive: ensure the Draft state exists (PCR workflow doesn't use it).
    if not frappe.db.exists("Workflow State", "Draft"):
        frappe.get_doc({
            "doctype": "Workflow State",
            "workflow_state_name": "Draft",
            "style": "Primary",
        }).insert(ignore_permissions=True)

    bulk_transitions = [
        ("Draft",                   "Submit",  "Pending Head of Finance", "LPG Head of Sales",   1),
        ("Pending Head of Finance", "Approve", "Approved",                "LPG Head of Finance", 0),
        ("Pending Head of Finance", "Reject",  "Rejected",                "LPG Head of Finance", 1),
    ]

    if not frappe.db.exists("Workflow Action Master", "Submit"):
        frappe.get_doc({
            "doctype": "Workflow Action Master",
            "workflow_action_name": "Submit",
        }).insert(ignore_permissions=True)

    frappe.get_doc({
        "doctype": "Workflow",
        "workflow_name": name,
        "document_type": "LPG Bulk Price Upload",
        "workflow_state_field": "workflow_state",
        "is_active": 1,
        "send_email_alert": 0,
        "states": [
            {"state": s["state"], "doc_status": s["doc_status"], "allow_edit": s["allow_edit"]}
            for s in bulk_states
        ],
        "transitions": [
            {
                "state": t[0],
                "action": t[1],
                "next_state": t[2],
                "allowed": t[3],
                "allow_self_approval": t[4],
            }
            for t in bulk_transitions
        ],
    }).insert(ignore_permissions=True)


# ----- Hook entrypoints -----------------------------------------------

def after_install():
    install_lpg_workflow()


def after_migrate():
    install_lpg_workflow()
