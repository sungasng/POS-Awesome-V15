# 04 — New Outlet Setup

End-to-end playbook for bringing a new Sungas outlet online in ERPNext +
POS Awesome. Split into **Functional Steps** (HR/Finance — what info to
gather) and **Technical Steps** (IT — what to run on the bench).

Average rollout: **1.5 days end-to-end** if all functional data is ready.

## Section A — Functional Steps (Finance / HR)

Before IT can begin, collect this info:

### 1. Outlet identity

| Field | Example | Source |
|---|---|---|
| Outlet name | "Apapa" | Ops |
| Account number prefix | `71` (next free 2-digit) | Finance (Chart of Accounts) |
| Address | "12 Wharf Road, Apapa, Lagos" | Ops |
| Region / Territory parent | "Lagos Mainland" | Sales |
| Manager | Plant Manager hire | HR |
| Number of cashiers | 2–3 typical | HR |

### 2. Banking & cash handling

| Field | Notes |
|---|---|
| Cash account | New `Cash - Apapa - SCL` (auto-created) |
| Transfer account | Outlet's primary bank — get account # from Finance |
| POS-Incoming account | Auto-created |
| Cash pickup vendor | If using armoured pickup — name + collection days |
| Daily lodgement bank | If self-deposit |

### 3. Sales / pricing

| Field | Notes |
|---|---|
| LPG tier rates | Retail / Bulk / Wholesale ₦/kg — match nearest region or set new |
| Cylinder prices | National default — no action unless promo |
| Cost Center prefix | Outlet gets `<NN>001` Operations + `<NN>002` Sales & Marketing |

### 4. HR

| Field | Notes |
|---|---|
| Branch record | "Apapa" — Frappe Branch doctype |
| Department | Default to existing (no per-outlet department) |
| Employees | Create via `Employee` doctype with `branch = Apapa` |
| POS Profile assignment | Map each cashier to POS Profile (Section B Step 5) |

## Section B — Technical Steps (IT)

### Step 1: Cost Centers

Add two new CCs in `Accounts > Cost Center`:

```
71001 - Operations Apapa - SCL          (under 71000 - 71999 - Apapa)
71002 - Sales and Marketing Apapa - SCL (under 71000 - 71999 - Apapa)
```

Or script:
```python
# Add to NEW_CCS in scripts/step2c3_assignments.py and re-run.
```

### Step 2: Chart of Accounts

Most outlet-specific accounts auto-create via the POS Profile script.
Manually verify these exist post-script:

| Account | Type |
|---|---|
| `Cash - Apapa - SCL` | Asset (Cash) |
| `POS-Incoming - Apapa - SCL` | Asset (Cash) |
| `Transfer - Apapa - SCL` | Asset (Bank) |
| `Sales LPG - Apapa - SCL` | Income |
| `Sales Cylinder - Apapa - SCL` | Income |
| `Sales Accessories - Apapa - SCL` | Income |
| `COGS LPG - Apapa - SCL` | Expense |

If missing, run `scripts/create_outlet_accounts.py` (copy of an existing outlet's account creator).

### Step 3: Warehouse

```
Apapa - SCL          (Warehouse type: Stock)
  ├── Apapa LPG Tank - SCL          (Stock — LPG only)
  └── Apapa Cylinders - SCL         (Stock — cylinders & accessories)
```

### Step 4: Branch (HR)

`HR > Branch > New`: Name = "Apapa". This auto-links Employees and HR docs.

### Step 5: Territory

`Selling > Territory > New`:
- Name: "Apapa"
- Parent: "Lagos Mainland" (or appropriate region)

### Step 6: Customer Groups + Default Customer

ERPNext default group `Retail` already exists. To create a per-outlet default
walk-in customer:

```
Customer = "Walk-in Apapa"
  - Customer Group: Retail
  - Territory: Apapa
  - Default Currency: NGN
```

### Step 7: POS Profile

Clone an existing profile via `scripts/clone_pos_profiles_to_outlets.py`:

```python
# Edit OUTLET_CASHIER_MAP:
OUTLET_CASHIER_MAP = {
    "Apapa": ["cashier.apapa.1@sungas.org", "cashier.apapa.2@sungas.org"],
    # ... existing outlets
}
```

Then:
```bash
curl -fsSL "<raw url>/scripts/clone_pos_profiles_to_outlets.py" -o /tmp/clone.py
bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/clone.py').read())"
```

This creates `POS - Apapa` with:
- `warehouse = Apapa - SCL`
- `cost_center = 71002 - Sales and Marketing Apapa - SCL`
- Payment methods wired to outlet Cash + Transfer + POS-Incoming
- HRMS Branch = "Apapa"
- Cashiers added to `pos_users` child table

### Step 8: LPG Outlet Price Tiers

Add 4 tier rows (Retail / Bulk / Wholesale / Reseller) to
`scripts/seed_all_lpg_tier_rates.py`:

```python
TIER_RATES["Apapa - SCL"] = {
    "Retail":     1360,
    "Bulk":       1340,
    "Wholesale":  1320,
    "Reseller":   1310,
}
```

Run on bench.

### Step 9: Cashier provisioning

For each cashier:

1. `User > New`:
   - Email: `cashier.apapa.1@sungas.org`
   - Role Profile: `LPG POS User`
   - Temporary password: `SungasOnboard@2026` (force-change on first login)
2. Add to POS Profile `pos_users` (handled by Step 7 script).
3. Add User Permission: `Customer Group = Retail` (so they only see Retail customers).

Use `scripts/create_missing_cashiers.py` as a template (one-shot for new outlets).

### Step 10: Plant Manager

1. Create User: `manager.apapa@sungas.org`
2. Role Profile: `LPG Plant Manager`
3. Assign Branch = `Apapa` via User Permission.
4. Create Employee record linking the User.

### Step 11: HR + Salary Structure Assignment

If new staff need to be on June 25 payroll:

1. Create Employee records with `branch = Apapa`, `status = Active`.
2. Set `payroll_cost_center = 71001 - Operations Apapa - SCL` (or 71002 for Sales).
3. Create Salary Structure Assignment from `Sungas Standard` (use
   `scripts/step3a_fix_ssa_bases.py` pattern to script the bulk insert).

### Step 12: Print Format

`Sungas Thermal 58mm` is shared across outlets. New outlet automatically
inherits — no action needed unless customizing per-outlet header.

### Step 13: Smoke test

Run the regression suite:
```bash
curl -fsSL "<raw url>/scripts/phase5_smoke_test.py" -o /tmp/smoke.py
bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/smoke.py').read())"
```

Expect all 27 cases pass. Then manually:

1. Cashier logs in at `/posawesome`.
2. Opens shift with ₦0 cash.
3. Sells 1kg LPG to walk-in Retail customer (₦1,360).
4. Closes shift, confirms balance.
5. Plant Manager approves close.
6. Finance verifies GL: Cash Dr ₦1,360 / Sales LPG Cr ₦1,360.

If all green → outlet is live. Communicate to Ops + HoS.

## Rollback procedure

If an outlet setup is botched and needs cleanup before re-doing:

1. Disable POS Profile (`disabled=1`).
2. Mark cashier users `enabled=0`.
3. Cancel any test POS Invoices.
4. Delete via UI: POS Profile → Warehouse → Territory → Branch → Cost Centers
   (in that order; ERPNext blocks delete if dependencies exist).
5. Re-run the full Section B from Step 1.

## Estimated time per step

| Step | Time | Owner |
|---|---|---|
| Section A (info gathering) | 1 day | Ops + Finance + HR |
| Steps 1–6 (accounts, branches) | 30 min | IT |
| Steps 7–8 (POS Profile, tiers) | 30 min | IT |
| Steps 9–11 (users + employees) | 1–2 hours | IT + HR |
| Step 13 (smoke test) | 30 min | IT + Plant Mgr |
| **Total IT effort** | **~3 hours** | |
