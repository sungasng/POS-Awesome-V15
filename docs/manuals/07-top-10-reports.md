# 07 — Top 10 Reports

The essential reports for Sungas operations. Each has: purpose, how to access,
key columns, and how to interpret.

## 1. Daily Sales Summary by Outlet

**Path**: `Reports > Sales Register` → filter by date + filter by `cost_center like 'XX002%'` (Sales & Marketing CCs).

**Purpose**: How much did each outlet sell today?

**Key columns**: Outlet (via Cost Center), Customer, Item, Qty, Rate, Total, Customer Group.

**Interpret**: Compare Cash + Transfer + Card columns. Bulk vs Retail breakdown.
If Bulk = 0 at a non-bulk outlet (most outlets), it's expected (Bulk is HQ/wholesale only).

> Schedule it: Reports > Auto Email Report > daily at 7am to Head of Sales + Plant Managers.

## 2. POS Closing Shift Report

**Path**: `Selling > POS Closing Shift > List` → filter `status = Submitted`, `posting_date = today`.

**Purpose**: Daily reconciliation. Did cashier closing match expected?

**Key columns**: Cashier, Opening Balance, Expected Closing, Actual Closing, Difference Amount, Notes.

**Interpret**:
- 0 difference: ideal
- ±₦200: acceptable (rounding/disputes)
- ±₦200 to ±₦2,000: investigate
- > ±₦2,000: escalate to Internal Control

## 3. Stock Balance by Outlet

**Path**: `Stock > Stock Balance` → filter by warehouse parent or by Item Group.

**Purpose**: How much LPG / cylinders does each outlet have RIGHT NOW?

**Key columns**: Warehouse, Item Code, Item Name, Available Qty, Stock UOM, Valuation Rate.

**Interpret**:
- LPG kg per outlet — refill triggers (e.g., reorder when < 5,000 kg)
- Cylinder counts per size — anti-stockout alert
- Negative Qty = data integrity issue → run Stock Reconciliation

## 4. Stock Ledger — Item × Warehouse

**Path**: `Stock > Stock Ledger Report`.

**Purpose**: Every movement of a specific item in/out of a warehouse.

**Key filters**: Item, Warehouse, From Date, To Date.

**Interpret**:
- Auditable trail for any kg discrepancy
- Links to source doc (Stock Entry, POS Invoice, Material Issue, etc.)

## 5. Gross Profit per Outlet

**Path**: `Accounts > Profitability Analysis` → filter by Cost Center range.

**Purpose**: Which outlet is most profitable? Spot loss-making outlets fast.

**Key columns**: Sales (revenue), COGS, Gross Profit, Gross Margin %.

**Interpret**:
- Healthy LPG outlet should see 15–25% gross margin
- < 10% indicates pricing issue (Bulk customers leaking into Retail?)
- > 30% suggests undercosting (check Item COGS calc)

## 6. Outstanding Receivables

**Path**: `Accounts > Accounts Receivable Summary` → filter Customer Group = "Bulk" / "Wholesale" (Retail is cash-on-sale; AR should be near zero).

**Purpose**: Who owes Sungas money and how aged?

**Key columns**: Customer, 0-30 days, 31-60, 61-90, 91-120, > 120, Total.

**Interpret**:
- Bulk/Wholesale customers carrying balances > 60 days → freeze account, escalate to Finance
- Retail AR > ₦0 → likely cashier error (sale on credit not allowed)

## 7. Salary Register

**Path**: `HR > Salary Register` → filter by month.

**Purpose**: Per-employee payslip view + PAYE tracking.

**Key columns**: Employee, Gross Pay, Pension EE, PAYE, Net Pay, Cost Center.

**Interpret**:
- Cross-check PAYE against NTAA 2025 brackets manually for 5 random employees
- Verify Cost Center routing (no Operations staff posting to Sales CC)

## 8. Trial Balance

**Path**: `Accounts > Trial Balance` → date range.

**Purpose**: GL health check. Debits must = Credits.

**Interpret**:
- Difference ≠ 0 = data integrity issue (unposted journal, mid-write crash)
- Run weekly. If imbalance, contact IT.

## 9. Item Price History (Audit)

**Path**: `Selling > Item Price > List` → click any row → Connections > Version (top right).

**Purpose**: Who changed which price, when?

**Interpret**:
- Audit HoS Sales pricing changes
- Track tier changes that affect margins

## 10. Login Activity Log

**Path**: `Setup > Activity Log` → filter `operation = Login` or filter by `user`.

**Purpose**: Security audit. Who logged in when, from what IP?

**Interpret**:
- Out-of-hours logins (3am cashier? suspicious)
- Multiple failed logins → potential brute-force, contact IT
- Geographic anomaly (Lagos cashier logging from Abuja → escalate)

## Scheduling reports

Most can be auto-emailed:

1. Open any List view.
2. `Menu (⋮) > Save Filter As New Auto Email Report`.
3. Set:
   - Frequency: Daily / Weekly / Monthly
   - Recipients: HoS, HoF, Plant Managers
   - Format: HTML inline + Excel attachment
4. Save.

Recommended schedule:

| Report | Frequency | To |
|---|---|---|
| Daily Sales Summary | Daily 7am | HoS, all Plant Mgrs |
| POS Closing Shift | Daily 8am | Plant Mgrs, HoF |
| Stock Balance | Daily 7am | Stores, Plant Mgrs |
| Gross Profit | Weekly Mon 8am | HoS, HoF, MD |
| Outstanding AR | Weekly Fri 5pm | HoF, Sales team |
| Salary Register | Monthly 26th | HR, HoF |
| Trial Balance | Weekly Mon 9am | HoF, Internal Control |
| Login Activity | Weekly Mon 9am | IT, Internal Control |
