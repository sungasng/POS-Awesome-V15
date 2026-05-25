# Sungas ERPNext v15 — Upgrade Safety Checklist

When Frappe Cloud pushes a new ERPNext / HRMS / Frappe core version (or our team clicks "Update Apps"), run this checklist **on a sandbox bench first**, never directly on production.

---

## What survives a Frappe core update (DB-level)

These are stored as DB rows, not source files. Frappe never overwrites them on update:

- **Custom Fields**: `Employee.rent_paid_annually`, `grade_level`, `eligible_for_13th_month`, `hmo_monthly_premium_company_paid`, `hmo_monthly_topup_staff_paid`, `payroll_cost_center`. Bank: `nibss_code`, `bank_category`.
- **Salary Components** (12): Basic Pay, Housing, Transport, COLA, Medical, Leave Allowance, 13th Month, NSITF, Pension EE/ER, PAYE, HMO Top-up + COOP + Loan.
- **Salary Structure**: `Sungas Standard` (10 row-level formulas restored 2026-05-23).
- **Salary Structure Assignments**: 216 active SSAs effective 2026-05-01.
- **Workflows**: Leave / Expense (tiered) / Payroll Entry — all `is_standard = "No"`.
- **Server Scripts**: `Sungas - Force Retail Group On Customer Insert`, `Sungas - Block Customer Edits By Cashier`.
- **Print Formats**: `Sungas Thermal 58mm` (POS receipt), `Sungas Payslip` (salary slip). Both `is_standard = "No"`, `custom_format = 1`, `module = "Custom"`.
- **POS Profiles** (22), **Holiday Lists** (2), **Leave Types** (6), **Leave Policies** (3), **Cost Centres** (21 outlet), **Branches** (HRMS), **Accounting Dimensions**, **Roles & Role Profiles** (4 LPG), **Bank** master (45 NIBSS-coded), **User Permissions**.
- **POS Awesome customizations** in `apps/posawesome` — pinned to branch `feat/sungas-customizations`, only fast-forwards if there's a new commit on **our** branch.

## What gets overwritten (and how we stay safe)

- **Core app code**: `apps/frappe`, `apps/erpnext`, `apps/hrms` are wiped & replaced. We have **no patches** in core code — everything is via the layers above.
- **Standard Print Formats / Workflows / Server Scripts** with `is_standard = "Yes"` are replaced. We never edit these in-place.
- **Doctype schema migrations** add/remove fields per the new HRMS version — DB data on those fields persists.

---

## Pre-upgrade checklist

Run these on the **sandbox** bench AFTER the upgrade is applied there:

### 1. Smoke checks (5 min)

```bash
# Confirm POS Awesome branch + commits intact
cd ~/frappe-bench/apps/posawesome && git status && git log -3 --oneline

# Confirm core custom fields exist
bench --site sandbox.frappe.cloud execute "frappe.db.get_value" \
  --kwargs "{'doctype': 'DocField', 'filters': {'parent': 'Employee', 'fieldname': 'rent_paid_annually'}, 'fieldname': 'name'}"
# Expect: a Custom Field name, not None.
```

### 2. Salary Structure health (30 sec)

```bash
SHA=<latest commit>
curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/$SHA/scripts/step8b_diagnose_deep.py" -o /tmp/diag.py
bench --site sandbox.frappe.cloud execute "exec(open('/tmp/diag.py').read())"
```
Verify the dump still shows:
- `Sungas Standard` rows: `Basic Pay base*0.40`, `Housing base*0.25`, `Transport base*0.25`, `COLA base*0.10`, `NSITF base*0.01`, `Pension EE (BS+HA+TA)*0.08`, `Pension ER (BS+HA+TA)*0.10`, PAYE full NTAA formula.
- `make_salary_slip` in-memory produces non-zero earnings + deductions for HR-EMP-00002.

If any formula is empty → HRMS update wiped the row formula again. Re-run:
```bash
curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/$SHA/scripts/step8b_restore_formulas.py" -o /tmp/rf.py
sed -i 's/^DRY_RUN = True$/DRY_RUN = False/' /tmp/rf.py
bench --site sandbox.frappe.cloud execute "exec(open('/tmp/rf.py').read())"
```

### 3. Pre-flight on a current period (60 sec)

```bash
curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/$SHA/scripts/step8a_payroll_preflight.py" -o /tmp/pf.py
bench --site sandbox.frappe.cloud execute "exec(open('/tmp/pf.py').read())"
```
Verify aggregate Gross / PAYE / Pension / Net within 5% of the most recent month-end PE on prod. Any wild drift signals an HRMS calc engine change worth investigating.

### 4. Print formats render

Open `Sal Slip/HR-EMP-00002/00006` → Print → confirm "Sungas Payslip" still appears in the format dropdown and renders cleanly.
Open a POS Invoice → Print → confirm "Sungas Thermal 58mm" still renders with logo + barcode.

### 5. Server Scripts fire

Log in as a `LPG POS User` (test cashier credentials in `test_credentials.md`). Attempt to create a Customer with `Group = Bulk` → confirm it is forced to `Retail`. Attempt to edit an existing customer → confirm `ValidationError` blocks save.

### 6. Workflows apply

Create a draft Leave Application → confirm the 3-stage workflow is on it. Same for Expense Claim and Payroll Entry.

---

## Known v15 HRMS quirks (already mitigated)

| Quirk | Mitigation |
|---|---|
| `Salary Slip.set_salary_structure_assignment` filters by `payroll_payable_account` | step8b passes it explicitly; SSA auto-audit fixes drift |
| `Salary Slip.check_sal_struct` requires `from_date <= start_date` (strict `<=`) | step8b auto-backdates SSA `from_date` if > pe.start_date |
| Frappe Cloud `queue_action` sha224 lock files | `assign_cashier_roles.py` monkey-patches both `check_if_locked` + `lock` |
| Server Script `doctype_event` must be Title Case | All ours use `"Before Insert"`, `"Before Save"` |
| `safe_exec` sandbox lacks `frappe.get_roles` | Use `frappe.db.get_all('Has Role', ...)` |
| Salary slip `safe_eval` lacks `max`, `min`, `frappe`, hyphenated abbrevs (`PEN-EE`) | PAYE formula uses ternary chain + inlines pension as `(BS+HA+TA)*0.08` |
| `Print Format` needs `custom_format = 1` to use Jinja (else auto-generates) | All Sungas formats set this |
| Component-master formulas can wipe row-level on Draft save cycle | `step8b_restore_formulas.py` is idempotent — re-run after any structure edit |

---

## Rollback plan

If something breaks badly on the sandbox, do NOT upgrade production. Open Frappe Cloud support ticket with:
1. Sandbox URL + which step failed
2. Output of `step8b_diagnose_deep.py`
3. ERPNext + HRMS + Frappe version triple (Desk → About)
4. Latest commit SHA of `feat/sungas-customizations`

Frappe Cloud's rollback is automatic if you don't push the upgrade to prod.

---

_Last updated: 2026-05-23_
