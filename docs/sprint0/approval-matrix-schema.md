# Sungas Approval Matrix — DocType design

**Sprint 0 deliverable** — for your review before we build it in Phase A.

---

## Problem we're solving

The developer brief hardcodes approval thresholds in workflow logic:

- Weekly engagement budget per officer → Line Manager  
- Monthly engagement budget → Line Manager + Finance + COO  
- Customer asset disposal → COO  
- Campaign approval → CC Supervisor / HO Sales

You flagged correctly: **these must be configurable in the UI**, not buried in Python. Finance and HR change them every fiscal year, sometimes mid-year, and engineers should not be on the critical path for a routine policy update.

## Solution: Two-layer model

### Layer 1: Default thresholds — `SCL Approval Matrix` (Single DocType)

A singleton DocType with a child table. One row per (workflow × threshold).

```
SCL Approval Matrix
├── matrix_version (Auto)          # incremented on every save (audit trail)
├── effective_from (Date)          # when this version starts to apply
├── effective_to (Date, optional)  # null = currently active
├── notes (Long Text)              # "Changed weekly cap from 50K to 75K per COO memo dated..."
└── thresholds (Table → SCL Approval Threshold)
       ├── workflow_key (Select)
       │     ▸ engagement_plan_weekly
       │     ▸ engagement_plan_monthly
       │     ▸ engagement_plan_quarterly
       │     ▸ expense_claim_default
       │     ▸ expense_claim_capital
       │     ▸ customer_asset_disposal
       │     ▸ campaign_calendar
       │     ▸ refund_credit_note
       │     ▸ price_override
       │     ▸ pos_discount_override
       ├── threshold_amount_ngn (Currency)
       ├── approver_role (Link → Role)
       ├── requires_second_approver (Check)
       ├── second_approver_role (Link → Role, conditional)
       ├── auto_create_expense_claim (Check)   # for engagement plan items
       └── notification_recipients (Small Text)  # comma-separated user IDs
```

### Layer 2: Per-employee overrides — Custom Fields on Employee

Sometimes a senior CSE has a ₦150K weekly cap while a junior CSE has ₦50K. Three Custom Fields on Employee, HR-Manager-only edit:

```
Employee
├── weekly_engagement_budget_ngn (Currency, default 0 = use matrix default)
├── monthly_engagement_budget_ngn (Currency, default 0 = use matrix default)
└── approval_authority_ngn (Currency, default 0)
       # how much THIS employee can approve as a line manager
       # 0 = use role default from matrix
```

### Resolution logic at runtime

```python
def get_threshold(workflow_key, employee=None):
    # 1. Check employee-specific override
    if employee:
        custom_field = {
            "engagement_plan_weekly": "weekly_engagement_budget_ngn",
            "engagement_plan_monthly": "monthly_engagement_budget_ngn",
        }.get(workflow_key)
        if custom_field:
            val = frappe.db.get_value("Employee", employee, custom_field)
            if val and val > 0:
                return val
    # 2. Fall back to matrix default
    matrix = frappe.get_single("SCL Approval Matrix")
    for row in matrix.thresholds:
        if row.workflow_key == workflow_key:
            return row.threshold_amount_ngn
    raise frappe.ValidationError(f"No threshold configured for {workflow_key}")
```

## Initial population (defaults for review)

I propose these starter values for Finance / COO sign-off:

| Workflow | Default ₦ | First approver | Second approver |
|---|---|---|---|
| Engagement Plan — weekly cap | 50,000 | Line Manager | — |
| Engagement Plan — monthly cap | 150,000 | Line Manager | Finance Head |
| Engagement Plan — quarterly cap (per CSE) | 400,000 | Finance Head | COO |
| Expense Claim — default | 25,000 | Line Manager | — |
| Expense Claim — capital (over) | 100,000 | Finance Head | COO |
| Customer asset disposal | any | COO | — |
| Campaign Calendar publish | any | CC Supervisor OR HO Sales | — |
| Refund / Credit Note | 20,000 | Finance Officer | Finance Head if > 20K |
| POS line discount override | 5% | Cashier | Plant Manager if > 5% |
| Price override on Sales Order | 10% | Sales Officer | HO Sales if > 10% |

**Please review and adjust** before we seed.

## Audit trail

- `matrix_version` auto-increments on every save (via `before_save` hook)
- Full history kept (DocType has `track_changes=1`)
- Versions are queryable: "what was the weekly cap on 2026-03-15?" answers in one query
- Each approval action records `matrix_version_at_decision` on the source doc

## Permissions

| Role | View | Edit |
|---|---|---|
| HR Manager | ✓ | ✗ |
| Accounts Manager | ✓ | ✗ |
| Finance Head | ✓ | ✓ (for finance thresholds only) |
| COO | ✓ | ✓ (all) |
| System Manager | ✓ | ✓ (all) |
| Everyone else | ✗ | ✗ |

The "Finance thresholds only" restriction is enforced via permission level — finance-tagged rows in the child table have a higher `permlevel` than COO-only rows.

## Migration path for existing payroll thresholds

The PAYE / Pension / NSITF percentages we restored in `step8b_restore_formulas.py` are **also configurable thresholds** if Finance wants them in the UI. I'd argue against it though:

- They're set by Nigerian statute (NTAA 2025, NSITF Act, Pension Reform Act), not by Sungas policy
- Changing them mid-year via UI risks payroll error
- Better: keep them in code, hash-locked, with the upgrade checklist requiring a re-run of `step8a_payroll_preflight.py` whenever the structure changes

If you disagree, we can add a "Payroll Formula Versions" tab to the matrix — but recommend keeping payroll formulas out for now.

## Open questions for you

1. **Approval delegation** — if a Line Manager is on leave, can the COO approve directly, or must HR temporarily reassign? (NDPA-style "automated decision-making" rules say yes, but Sungas's internal policy may differ.)
2. **Multi-currency** — all in NGN, or do we anticipate USD-denominated thresholds for the Bulk segment? Currency field on each row?
3. **Time-bound thresholds** — Christmas / year-end bonuses sometimes need higher caps. Add `valid_from` / `valid_to` per row, or treat as a one-off override via a memo?
4. **Approval workflow notifications** — should approvers get an in-app notification, an email, or both? Brief says "Real-Time User Notification" — I default to both.
5. **Initial role mapping** — the brief mentions "SCL CC Supervisor", "SCL CSE", etc. Are these new roles, or should we map to existing ERPNext roles (e.g., "Sales Manager", "HR User")? Recommend new roles, prefixed `SCL ` for clarity.

---

## Next steps

When you've reviewed:

1. **Adjust the threshold defaults** in the table above
2. **Answer the 5 open questions**
3. I'll create the DocType JSON, child table JSON, fixtures with your approved defaults, and the resolution helper function — all in Phase A week 1

Then HR can change a threshold in the UI without an engineer in the loop. Forever.
