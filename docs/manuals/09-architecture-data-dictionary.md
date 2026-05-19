# 09 — Architecture & Data Dictionary

System reference for IT, new dev onboarding, and audit.

## Tech stack

| Layer | Component |
|---|---|
| Hosting | Frappe Cloud (managed Kubernetes) |
| Bench site | `sungasmis.v.frappe.cloud` |
| Framework | Frappe v15 |
| ERP | ERPNext v15 |
| POS | POS Awesome v15 (fork: `sungasng/POS-Awesome-V15`) |
| HR addon | HRMS v15 |
| Custom app: business logic | `sungas` (fork: `sungasng/Sungas`, branch `version-15`) |
| Custom app: HR | `hr_enhancements` (fork: `sungasng/HR-Enhancements`, branch `version-15`) |
| DB | MariaDB 10.6 (Frappe-managed) |
| Frontend | Vue 3 (POS Awesome), HTMX/Jinja (Frappe Desk) |
| Print engine | wkhtmltopdf + barcode (Code 128) |

## Custom apps

### `sungas`

Sungas-specific business logic + custom doctypes.

Doctypes:
- `LPG Outlet Price Tier` — tier matrix (warehouse × territory × customer_group → rate)
- `LPG Tank Capacity` — per-outlet tank calibration table (kg vs dipstick reading)
- `Sungas Region` — accounting dimension parent for region-level grouping

### `hr_enhancements`

Custom HR workflows.
- Approval routing logic for Leave / Expense / Payroll Entry
- Custom email templates for HR
- Phase 6 will activate this via Step 5 workflows.

### `posawesome` (this fork)

Sungas-specific customizations on top of upstream POS Awesome:
- Tier pricing injection (`api/items.py`)
- Cash-overage rounding (`apply_cash_overage`)
- Sungas Thermal 58mm receipt format
- Customer group lockdown (Server Scripts)

## Custom fields (Employee)

| Fieldname | Type | Source | Purpose |
|---|---|---|---|
| `state_of_residence` | Link → State | Phase 6 / 2a | NTAA 2025 PAYE jurisdiction |
| `hmo_coverage_type` | Select | Phase 6 / 2c.1 | HMO plan (Basic/Standard/Family) |
| `hmo_monthly_premium_company_paid` | Currency | Phase 6 / 2c.1 | Benchmark company contribution |
| `hmo_monthly_topup_staff_paid` | Currency | Phase 6 / 2c.1 | Staff top-up above benchmark |
| `payroll_cost_center` | Link → Cost Center | Phase 6 / 2c.3 | GL routing for salary expense |
| `rent_paid_annually` | Currency | Phase 6 / 3 | NTAA 2025 rent relief input |

## Custom fields (POS Profile / others)

| Doctype | Fieldname | Type | Purpose |
|---|---|---|---|
| POS Profile | `default_payment_account` | Link → Account | Per-outlet POS-Incoming routing |
| POS Profile | `posa_pos_invoice_mode` | Check | Cashier-friendly invoicing |
| POS Invoice Item | `posa_amount_due` | Currency | Cash-overage stash (Pinia mirror) |
| Customer | `customer_lockdown_role` | Data | (Used by Server Script) |

## Server Scripts

| Name | Event | Function |
|---|---|---|
| `Sungas - Force Retail Group On Customer Insert` | Customer / Before Insert | Force `customer_group=Retail` for cashier-created customers |
| `Sungas - Block Customer Edits By Cashier` | Customer / Before Save | Throw ValidationError for cashier edits |
| `Sungas - Auto-route Salary GL` | Salary Slip / Before Submit | Override default CC with `Employee.payroll_cost_center` |

## Salary Components (12 total)

### Earnings (5)
| Component | Abbr | Formula |
|---|---|---|
| Basic Pay | BS | 40% of gross |
| Transport Allowance | TA | 25% of gross |
| Housing Allowance | HA | 25% of gross |
| Cost of Living Allowance | COLA | 10% of gross |
| Medical Allowance | MA | Fixed component |

### Deductions (7)
| Component | Abbr | Formula |
|---|---|---|
| NSITF (employer) | NSITF | 1% of gross |
| Pension Employee | PEN-EE | 8% of (basic + transport + housing) |
| Pension Employer | PEN-ER | 10% of (basic + transport + housing) |
| **PAYE** | **PAYE** | NTAA 2025 6-bracket on annualised taxable |
| HMO Top-up (Staff Paid) | HMO-TU | `employee.hmo_monthly_topup_staff_paid` |
| Loan Repayment | LOAN-RP | Configured per-employee |
| COOP Loan Repayment | COOP-LN | Configured per-employee |
| Cooperative Contribution | COOP-CN | Configured per-employee |

## Cost Center hierarchy (post Phase 6)

```
SUNGAS COMPANY LIMITED - SCL          (root, is_group=1)
  ├── 11000 - 11999 - Ikeja - SCL
  │     ├── 11001 - Operations Ikeja - SCL
  │     └── 11002 - Sales and Marketing Ikeja - SCL
  ├── 12000 - 12999 - Pedro - SCL
  │     ├── 12001 - Operations Pedro - SCL
  │     └── 12002 - Sales and Marketing Pedro - SCL
  ├── ... (21 outlets)
  ├── 70001 - Finance - SCL
  ├── 70002 - Sales and Marketing HEAD OFFICE - SCL
  ├── 70003 - Procurement - SCL
  ├── 70006 - HR & Admin - SCL
  ├── 70010 - Internal Control - SCL
  ├── 70011 - Executive - SCL
  └── 70013 - Operations Headquarters - SCL
```

## Chart of Accounts (key accounts)

### Assets (per outlet)
- `Cash - <Outlet> - SCL`
- `Transfer - <Outlet> - SCL`
- `POS-Incoming - <Outlet> - SCL`
- `Stock In-Hand - <Outlet> - SCL`
- `Staff Loan Receivable - SCL`

### Liabilities
- `Pension Payable - SCL`
- `PAYE Payable - SCL`
- `NSITF Payable - SCL`
- `HMO Payable - SCL` (custom, Phase 6)
- `Cooperative Loan Payable - SCL` (custom, Phase 6)
- `Cooperative Contribution Payable - SCL` (custom, Phase 6)

### Income (per outlet)
- `Sales LPG - <Outlet> - SCL`
- `Sales Cylinder - <Outlet> - SCL`
- `Sales Accessories - <Outlet> - SCL`

### Expenses
- `Salary Expense - SCL` (parent)
- `Pension Expense (Employer) - SCL`
- `Loss on Stock - SCL`
- `Stock Adjustment - SCL`

## Customer Groups

| Group | Tier in LPG Outlet Price Tier | POS access |
|---|---|---|
| Retail | "Retail" | ✓ (cashiers locked to this) |
| Bulk | "Bulk" | ✗ (Sales Invoice only) |
| Wholesale | "Wholesale" | ✗ (Sales Invoice only) |
| Reseller | "Reseller" | ✗ (Sales Invoice only) |

## Territories

22 territories total, one per outlet + "Headquarters" + regional parents
(Lagos Mainland, Lagos Island, Ogun, Benin, Asaba, Eleme).

## Role Profiles

| Profile | Roles Included |
|---|---|
| `LPG POS User` | POS User, Customer (read-only), POS Opening/Closing Shift, POS Invoice |
| `LPG Plant Manager` | LPG POS User + Item Manager (read), Stock Manager, Employee Self Service |
| `LPG Head of Sales` | Plant Manager + Item Price (write), Customer (write), Quotation |
| `LPG Head of Finance` | Plant Manager + Accounts Manager, Journal Entry, Payment Entry |

## Cron jobs (scheduled tasks)

Verify via `Setup > Scheduled Job Type > List`:

- `frappe.email.queue.flush` — every 5 min
- `frappe.utils.background_jobs.gc` — hourly
- `erpnext.accounts.utils.create_payment_gateway_account` — daily
- Sungas custom: (none currently — Phase 6 / Step 6 will add bank-upload generator)

## Key bench scripts inventory

Located in `scripts/`:

| Script | Phase | Purpose |
|---|---|---|
| `phase5_smoke_test.py` | 5 | 27-case POS regression |
| `clone_pos_profiles_to_outlets.py` | 5 | Bulk POS Profile rollout |
| `seed_all_lpg_tier_rates.py` | 5 | 64-row price matrix seed |
| `fix_customer_lockdown.py` | 5.5 | Server Script provisioning |
| `step1_*` | 6 | Employee audit |
| `step2a_*` | 6 | Master data backfill |
| `step2b_*` | 6 | Salary components |
| `step2c1_*` | 6 | HMO + structure |
| `step2c2_*` | 6 | GL mapping |
| `step2c3_assignments.py` | 6 | CCs + payroll_cost_center + 217 SSAs |
| `step3a_fix_ssa_bases.py` | 6 | 10x base bug fix |
| `step3b_residual_audit.py` | 6 | Token-fuzzy match for unmatched roster |
| `step3_paye_ntaa2025.py` | 6 | PAYE formula + rent field |
| `reassign_olise.py` | 6 | One-off employee reassignment |
| `_payroll_roster_v2.py` | 6 | Corrected roster data (217 emp) |

## GitHub repositories

| Repo | Branch (latest) | Last commit |
|---|---|---|
| `sungasng/POS-Awesome-V15` | `feat/sungas-customizations` | See `git log` |
| `sungasng/Sungas` | `version-15` | `7a95d5a` |
| `sungasng/HR-Enhancements` | `version-15` | `c802054` |

## Permissions inheritance

```
Administrator
  → System Manager   (all roles)
    → LPG Head of Finance / Head of Sales
       → LPG Plant Manager
          → LPG POS User (cashier)
```

Each level inherits the level below + adds its own.

## Database (logical)

| Table prefix | Purpose |
|---|---|
| `tabCustomer*` | Customers + groups + addresses |
| `tabItem*` | Items + pricing + BOMs |
| `tabSales Invoice*` | Sales transactions |
| `tabPOS Invoice*` | POS-specific sales (consolidated → Sales Invoice) |
| `tabEmployee*` | Employees + custom fields |
| `tabSalary*` | Components, structures, slips, assignments |
| `tabCost Center*` | CC hierarchy |
| `tabBin` | Per-warehouse Item Qty (denormalised) |
| `tabStock Ledger Entry` | Append-only movement log |
| `tabGL Entry` | Append-only GL log |

## Key data flows

### POS sale → GL
```
POS UI → POS Invoice (draft) → Submit
  ↓
Submit creates:
  ├── Stock Ledger Entry (Qty - source warehouse)
  ├── GL Entries (Cash/Transfer Dr, Sales Cr, VAT Cr)
  └── Update tabBin (denormalised Qty cache)
  ↓
End of shift:
  POS Closing Shift submit
  ↓
  POS Invoices auto-consolidated into Sales Invoice
  ↓
  Consolidated Sales Invoice posted to GL
```

### Salary slip → GL
```
Payroll Entry (HR/manager creates) → Submit
  ↓
For each Employee in scope:
  Salary Slip (draft) → Submit
  ↓
  Reads SSA.base → applies Sungas Standard formulas
  ↓
  Creates GL Entries:
    Salary Expense Dr (split by component)  -- CC = employee.payroll_cost_center
    Pension Payable, PAYE Payable, etc. Cr
    Net Pay Cr → Cash/Bank (on payment)
```

## Maintenance windows

Frappe Cloud auto-updates Saturdays 2-4am WAT (planned downtime ~10 min).
Schedule production code deploys outside this window.

## API endpoints (internal)

POS Awesome custom endpoints (defined in `posawesome/api/items.py`):
- `posawesome.api.items.get_items` — bulk item fetch
- `posawesome.api.items.get_item_detail` — single item with tier-aware pricing
- `posawesome.api.posawesome.get_pos_data` — POS Profile + customer + warehouse meta

All Frappe doctypes also expose REST automatically (`/api/method/frappe.client.*`).

## Audit log access

- `Setup > Activity Log` — all user actions (login, doc changes)
- `Setup > Version` — per-document change diff
- `Setup > Error Log` — exceptions

Retention: 90 days by default (configurable per doctype).
