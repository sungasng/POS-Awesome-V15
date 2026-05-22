# Step 8 — Parallel Payroll Run Runbook (June 2026)

**Goal:** Validate that ERPNext v15 payroll output matches the legacy Excel
payroll for the **June 2026** cycle, then disburse via Stanbic IBTC + Fidelity
bank uploads.

**Hard deadline:** payment date **2026-06-25**.

This runbook is the practical companion to:

- `scripts/step8a_payroll_preflight.py` — read-only validation
- `scripts/step8b_payroll_create.py` — creates the Payroll Entry + Salary Slips
- `scripts/step8c_payroll_reconcile.py` — ERP vs Excel variance report
- `scripts/step6b_bank_upload.py`        — Stanbic / Fidelity CSV generator

---

## 0. Prerequisites (one-off, already complete)

| Step | What | Status |
|------|------|--------|
| 2c.3 | 21 Cost Centres + 212 SSAs submitted              | ✅ |
| 3    | PAYE NTAA 2025 brackets + `rent_paid_annually`     | ✅ |
| 3a   | 10× base-pay bug audited & corrected               | ✅ |
| 4    | Holiday Lists + Leaves + Leave Period 2026         | ✅ |
| 4c   | `Leave Allowance` + `13th Month` components hooked | ✅ |
| 5    | 3 workflows live (Leave / Expense / Payroll)       | ✅ |
| 6a   | 45 NIBSS bank codes seeded                         | ✅ |

---

## 1. Pre-flight — `step8a_payroll_preflight.py`

Read-only. Confirms calendars, components, SSA coverage, bank data quality, and
projects the aggregate cash-out using a Python replica of the PAYE NTAA 2025
formula.

```bash
curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/feat/sungas-customizations/scripts/step8a_payroll_preflight.py" -o /tmp/s8a.py
bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/s8a.py').read())"
```

**Outputs (also registered as private File docs in Desk):**

- `/tmp/step8a_payroll_preflight.md` — narrative summary
- `/tmp/step8a_payroll_preflight.csv` — per-employee projection
- `/tmp/step8a_payroll_skips.csv` — employees that will be skipped + reason

**Acceptance gate:**

- 0 employees in `step8a_payroll_skips.csv`, OR every entry has a documented
  HR exception (e.g., suspended, on leave without pay).
- Aggregate Net Pay matches the Excel grand total within ±NGN 1,000.
- All employees have a non-empty `payroll_cost_center`.

If the gate fails, fix HR data and re-run **8a** until clean.

---

## 2. Create the Payroll Entry — `step8b_payroll_create.py`

Default is `DRY_RUN=True` — print only, no DB writes.

```bash
curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/feat/sungas-customizations/scripts/step8b_payroll_create.py" -o /tmp/s8b.py
bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/s8b.py').read())"
```

Review `/tmp/step8b_payroll_create.csv`. When everything looks right, flip the
toggle and run again:

```bash
sed -i 's/^DRY_RUN = .*/DRY_RUN = False/' /tmp/s8b.py
bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/s8b.py').read())"
```

The script will print the new Payroll Entry name, e.g.
`HR-PRE-2026-00001`. **Copy that name** — you'll need it in steps 3 and 5.

The Payroll Entry stays in **Draft** with all Salary Slips in draft. The Step 5
workflow (`Sungas Payroll Approval`) routes it: HR Manager → Internal Control →
COO. Slips submit when the COO approves the Payroll Entry.

---

## 3. Reconcile against the Excel baseline — `step8c_payroll_reconcile.py`

### 3a. Prepare the Excel baseline CSV

Export the legacy Excel payroll to a CSV with **exactly** these columns:

```csv
employee,gross,paye,pension_ee,nhf,nhis,net
HR-EMP-00001,450000.00,52340.00,28000.00,7500.00,5250.00,357010.00
HR-EMP-00002,...
```

- `employee` MUST be the ERP Employee ID (`HR-EMP-NNNNN`).
- Currency: **NGN, no commas, no symbols, no thousand separators**.
- File path on the bench: `/tmp/payroll_excel_baseline.csv`.

Easiest upload route from the HR laptop:

```bash
# 1. Drop the file into Desk: File List -> "+ New" -> drag CSV (private)
# 2. SSH into bench server and copy from private files:
cp ~/frappe-bench/sites/sungasmis.v.frappe.cloud/private/files/payroll_excel_baseline.csv /tmp/
```

### 3b. Run the reconciliation

```bash
curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/feat/sungas-customizations/scripts/step8c_payroll_reconcile.py" -o /tmp/s8c.py
sed -i 's|^PAYROLL_ENTRY = .*|PAYROLL_ENTRY = "HR-PRE-2026-00001"|' /tmp/s8c.py
bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/s8c.py').read())"
```

Replace `HR-PRE-2026-00001` with the Payroll Entry name from Step 2.

**Outputs:**

- `/tmp/step8c_reconciliation.md` — readable summary
- `/tmp/step8c_reconciliation.csv` — full table with delta columns + `flagged`

**Acceptance gate:**

- `0 flagged` rows, OR every flagged row has a written reason from HR/Finance
  (e.g., "Excel had a typo", "ERP correctly applied 13th month accrual").
- Aggregate `Delta` row in the markdown summary is within ±NGN 1,000.
- `Only in Excel` and `Only in ERP` lists are both empty (no missing/extra
  employees).

---

## 4. Workflow approval

Once 8c is clean:

1. HR Manager opens the Payroll Entry → action **"Forward to Internal Control"**.
2. Internal Control reviews → action **"Forward to COO"**.
3. COO clicks **"Approve"** — Salary Slips submit automatically; payroll
   journal posts.

Email notifications fire at every transition (Step 5 enabled `send_email_alert`).

---

## 5. Bank disbursement — `step6b_bank_upload.py` (Stanbic + Fidelity)

After the Payroll Entry is **submitted** (Salary Slips docstatus=1):

### Stanbic IBTC

```bash
curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/feat/sungas-customizations/scripts/step6b_bank_upload.py" -o /tmp/s6b.py
sed -i 's|^PAYROLL_ENTRY = .*|PAYROLL_ENTRY = "HR-PRE-2026-00001"|' /tmp/s6b.py
sed -i 's|^BANK = .*|BANK = "STANBIC"|' /tmp/s6b.py
bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/s6b.py').read())"
```

→ `/tmp/bank_upload_stanbic_HR-PRE-2026-00001.csv`

### Fidelity

```bash
sed -i 's|^BANK = .*|BANK = "FIDELITY"|' /tmp/s6b.py
bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/s6b.py').read())"
```

→ `/tmp/bank_upload_fidelity_HR-PRE-2026-00001.csv`

Both files are also registered as **private File docs** in Desk for the Finance
team (search File List by name).

### Bank-portal upload

| Bank      | Required portal fields                                                            |
|-----------|------------------------------------------------------------------------------------|
| Stanbic   | "Bulk Salary Upload" — pick the CSV — confirm sender — review pre-validation       |
| Fidelity  | "Bulk Funds Transfer" — choose "Salary" template — pick CSV — review beneficiaries |

---

## 6. Sign-off checklist

- [ ] `step8a` skips list = empty (or each row signed off by HR Lead)
- [ ] `step8c` flagged rows = 0 (or each row signed off by HR + Finance)
- [ ] Aggregate ERP vs Excel delta within tolerance (±NGN 1,000)
- [ ] Stanbic CSV row count = Stanbic-bank employees with valid accounts
- [ ] Fidelity CSV row count = Fidelity-bank employees with valid accounts
- [ ] Stanbic + Fidelity totals reconcile to total Net Pay
- [ ] Internal Control + COO have approved the Payroll Entry workflow
- [ ] Bank uploads acknowledged by both portals
- [ ] Payslips emailed (Salary Slip "Email Salary Slip" bulk action)

---

## 7. Rollback

If a serious variance is found **after** the Payroll Entry is submitted but
**before** disbursement:

1. COO cancels the Payroll Entry (this also cancels child Salary Slips).
2. Fix the underlying SSA / Salary Component / Employee data.
3. Re-run from Step 1 (8a → 8b → 8c → workflow → 6b).

If disbursement has already happened, **do not** cancel — book a Journal Entry
to adjust the ledger and treat the difference as a manual reversal.
