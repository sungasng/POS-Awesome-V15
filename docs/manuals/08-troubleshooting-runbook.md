# 08 — Troubleshooting Runbook

Quick reference for common issues across POS, payroll, stock, and accounts.
Each entry: **Symptom → Probable cause → Fix steps**.

## POS Awesome

### "Sale blocked — no tier" toast appears at PAY

**Symptom**: Cashier clicks PAY on LPG line, toast says "Sale blocked — no tier defined."

**Cause**: Strict tier mode (Phase 5 commit `450f3a9`) — POS refuses sale if no
`LPG Outlet Price Tier` row matches (warehouse × territory × customer_group).

**Fix**:
1. Verify the customer's Customer Group + Territory.
2. Open `Selling > LPG Outlet Price Tier > List`, filter by warehouse.
3. If row missing → HoS adds it via `seed_all_lpg_tier_rates.py`.

### Receipt prints generic Frappe format instead of Sungas Thermal

**Symptom**: Receipt shows table layout, no logo, no barcode.

**Cause**: Frappe v15 Print Format custom format flag missing.

**Fix**:
```bash
bench --site sungasmis.v.frappe.cloud execute "
import frappe
pf = frappe.get_doc('Print Format', 'Sungas Thermal 58mm')
pf.custom_format = 1
pf.save()
"
```

### Cart shows ₦0 rate even though Item Price exists

**Symptom**: LPG line in cart has 0 rate.

**Cause**: Frontend not passing `customer` to `get_items_details`.

**Fix**:
- Check `frontend/src/posapp/composables/useItem.ts` line ~120 — ensure
  `customer: customer.value?.name` is in the params.
- Reference commit: `26154f3`.

### Cashier can edit existing customer

**Symptom**: Cashier opens an existing Bulk customer and saves changes.

**Cause**: Server Script `Sungas - Block Customer Edits By Cashier` disabled or
`doctype_event` set to snake_case (silently doesn't fire).

**Fix**:
1. `Setup > Server Script > List` — verify script enabled.
2. `doctype_event` MUST be "Before Save" (Title Case).
3. Re-run `scripts/fix_customer_lockdown.py`.

### POS-Awesome `requestAnimationFrame` console error

**Symptom**: Browser DevTools shows `requestAnimationFrame` errors on POS load.

**Cause**: Vue bundle minification artifact in upstream POS Awesome.

**Fix**: Harmless. Ignore unless paired with actual UI failures.

## Payroll

### Salary slip PAYE = 0 for high earner

**Symptom**: An employee earning ₦1M/mo has PAYE = 0.

**Cause**: One of:
- SSA `base` is 10x too small (Phase 6 / step 3a bug)
- Employee designation triggers non-exec director exclusion
- Effective date mismatch — slip dated before `Sungas Standard` SSA effective

**Fix**:
1. Open the SSA: confirm `base` matches expected monthly gross.
2. Check `Employee.designation` — if matches `Chairman/Non-Executive Director`,
   the PAYE condition excludes them by design.
3. Check Salary Slip `start_date` ≥ SSA `from_date` (2026-06-01).
4. Re-run `scripts/step3a_fix_ssa_bases.py` if base is wrong.

### Cost Center missing on salary GL

**Symptom**: Salary Slip GL entries post but no Cost Center → P&L bucketing broken.

**Cause**: `Employee.payroll_cost_center` field empty.

**Fix**: Re-run the routing pass in `scripts/step2c3_assignments.py` (idempotent, only updates missing).

### PAYE formula throws "name not defined"

**Symptom**: Salary Slip submission fails with `NameError: PEN_EE is not defined`.

**Cause**: `Pension Employee` component abbr changed or missing from structure.

**Fix**:
1. Verify component abbr = `PEN-EE` (Frappe converts hyphen to underscore in formula).
2. Confirm `Pension Employee` is in `Sungas Standard` Deductions table.

## Stock & Inventory

### Negative stock blocks new POS sale

**Symptom**: POS PAY button errors "Negative stock not allowed for item LPG-REFILL at warehouse Pedro LPG Tank".

**Cause**: Stock count drifted below 0 (e.g., refill not recorded yet, daily sales eat into next-day's planned stock).

**Fix**:
1. Stores Officer must enter Material Receipt for the latest refill.
2. Or temporarily allow negative stock at Company level (`Allow Negative Stock=1`)
   — but this masks the underlying recording lag. Not recommended.

### Stock Ledger and Stock Balance disagree

**Symptom**: Stock Balance shows 0 kg, Stock Ledger shows running total.

**Cause**: Bin record out of sync (rare; usually after server crash mid-write).

**Fix**:
```bash
bench --site sungasmis.v.frappe.cloud repost-item-valuation
```

## Accounts

### Trial Balance not balanced

**Symptom**: `Trial Balance` report shows non-zero Difference at bottom.

**Cause**: Unposted Journal Entry, draft Sales Invoice, mid-write crash.

**Fix**:
1. `Accounts > General Ledger` → filter `voucher_type = Journal Entry, docstatus = 0`. Submit or cancel each.
2. Same for Sales / Purchase Invoices.
3. If still imbalanced → contact IT for raw SQL audit.

### Cost Center missing on auto-posted GL

**Symptom**: GL Entry has no Cost Center → revenue not attributed to outlet.

**Cause**: POS Profile `cost_center` field empty, or Item Default missing.

**Fix**:
1. `Selling > POS Profile > <outlet>` — confirm `cost_center` filled.
2. If Items missing default account → re-run `scripts/wire_round_off_account.py`-style fix.

## HR / Permissions

### Cashier sees other outlet's customers

**Symptom**: Cashier at Pedro can see Walk-in Ikeja customer.

**Cause**: User Permission missing — `Customer Group = Retail` was applied, but
`Territory = Pedro` was not.

**Fix**: `User > <cashier> > User Permissions`:
- Customer Group = Retail
- Territory = <Outlet name>

### Employee not appearing in Payroll Entry

**Symptom**: Payroll Entry "Get Employees" returns < expected count.

**Cause**:
- Employee status ≠ Active
- No submitted Salary Structure Assignment for the payroll month
- Joining Date > payroll cycle end date

**Fix**:
1. `HR > Employee > List` — filter `status=Active`, confirm count.
2. `HR > Salary Structure Assignment` — filter `docstatus=1`, confirm 217+ rows.
3. Re-run `scripts/step3a_fix_ssa_bases.py` or `step3b_residual_audit.py`.

## Bench / Frappe Cloud

### `bench execute` traceback "App is not installed"

**Symptom**: All bench execute commands print a cosmetic traceback before output.

**Cause**: Frappe parses the `exec(...)` string as an app name first, fails,
then falls through to running the code.

**Fix**: Ignore — output below the traceback is the actual script result.

### `queue_action` errors trying to insert Role Profile / docs

**Symptom**: `frappe.exceptions.LockedDocument` when scripting Role Profile creation.

**Cause**: Frappe Cloud v15 `lock_doc` calls run BEFORE `flags.in_migrate`
short-circuit. SHA224-hashed lock filenames make manual cleanup impossible.

**Fix**: Monkey-patch in the script:
```python
import frappe
frappe.model.document.Document.check_if_locked = lambda self: None
frappe.model.document.Document.lock = lambda self, *a, **k: None
try:
    # ... do your work
finally:
    pass  # patches reset when bench process exits
```
Pattern in `scripts/assign_cashier_roles.py`.

### Hot-patch a Python file without redeploy

**Symptom**: Need to fix a tier-calc bug without waiting for Frappe Cloud "Update Apps".

**Fix**:
```bash
curl -fsSL "<raw github url>/posawesome/posawesome/api/items.py" -o ~/frappe-bench/apps/posawesome/posawesome/api/items.py
bench --site sungasmis.v.frappe.cloud clear-cache
bench restart
```

Use only for Python — Vue changes need full "Update Apps" rebuild.

## Authentication / Login

### "Invalid Password" on known-good credentials

**Symptom**: Cashier swears password is right but login fails.

**Cause**: Common — sometimes a paste includes a trailing whitespace, or the
account has been disabled.

**Fix**:
1. `Setup > User > <email>` — confirm `Enabled = 1`.
2. Reset password from admin panel, communicate new temp via Telegram/SMS.
3. Force password change on first login (`force_password_change=1`).

### Cashier locked out after many attempts

**Symptom**: User shows "Login disabled due to brute force".

**Fix**: `User > <email> > Account Info > Failed Login Attempts > Reset to 0`.

## CDN / GitHub

### Script change not reflected after push

**Symptom**: Pushed a fix, ran `curl` + `bench execute`, still old behaviour.

**Cause**: `raw.githubusercontent.com` caches ~5 min.

**Fix**: Pin to commit SHA:
```bash
curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/<commit-sha>/scripts/<file>.py"
```

## Logging

### Where do I find errors?

| Source | Location |
|---|---|
| Frappe error log | `Setup > Error Log` (in UI) |
| Supervisor stdout/stderr | Frappe Cloud doesn't expose; use bench `tail -f` if SSH'd |
| Server Script errors | `Setup > Server Script > <script> > Last Error` field |
| API call errors | `Setup > Activity Log` filtered by `subject like '%Exception%'` |

## Escalation matrix

| Issue severity | Owner | Channel |
|---|---|---|
| Cashier can't open shift (single outlet) | Plant Manager → IT | Telegram POS-Support group |
| Multi-outlet outage | IT → Head of Finance → MD | Phone immediately |
| Wrong PAYE on > 5 employees | HR → IT → Finance Mgr | Email + Slack #payroll |
| Trial Balance imbalance > ₦10k | Finance Mgr → IT | Email + scheduled fix |
| Suspected fraud / theft | Plant Mgr → Internal Control → MD | In-person + sealed memo |
