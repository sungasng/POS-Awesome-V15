# 01 — POS Shift Operations

Daily operations for cashiers and plant managers using POS Awesome at every
Sungas outlet.

## Roles

| Role | What they do |
|---|---|
| **Cashier** (`LPG POS User`) | Opens shift, takes sales, closes shift, prints Z-report |
| **Plant Manager** (`LPG Plant Manager`) | Approves close, investigates variance, escalates losses |
| **Head of Finance** | Daily GL reconciliation (next-day) |

## Workflow

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Open POS Shift │ →  │  Sales (POS UI) │ →  │ Close POS Shift │
│  (declare cash) │    │ (cash/transfer) │    │  (count cash)   │
└─────────────────┘    └─────────────────┘    └────────┬────────┘
                                                       │
                                                       ▼
                                              ┌─────────────────┐
                                              │ Reconcile diff. │
                                              │ (Plant Manager) │
                                              └────────┬────────┘
                                                       │
                                                       ▼
                                              ┌─────────────────┐
                                              │ Day-end GL post │
                                              │ (next morning)  │
                                              └─────────────────┘
```

## A) Opening Shift — Cashier

**Goal**: Declare opening cash float so end-of-day variance is calculable.

1. Log in to `https://sungasmis.v.frappe.cloud/posawesome` with cashier credentials.
2. Click **Open Shift**.
3. Select your POS Profile (auto-defaults — e.g. `POS - Pedro`).
4. Enter **Opening Cash Balance** = physical cash in till at start (₦).
5. Confirm POS Closing Voucher reference is empty (first shift of day).
6. Click **Confirm Opening**.

> **Expected**: shift status = `Open`, an entry appears in `POS Opening Shift` doctype.

### Common errors at open

| Error | Cause | Fix |
|---|---|---|
| "POS Profile is not active" | Profile disabled (e.g. `POS - Bulk Sales Benin`) | Use a different POS Profile assigned to you |
| "User not in pos_users child table" | Cashier mapping missing | Plant Mgr to add cashier in POS Profile > Cashiers |
| "No POS Profile assigned" | New cashier without Role Profile assignment | IT to assign `LPG POS User` Role Profile |

## B) Taking Sales — Cashier

1. Search item by name, barcode scan, or grid click.
2. Cart UI shows tier pricing automatically — for LPG, the cart line shows
   the customer's tiered rate (Retail / Bulk / Wholesale).
3. Quantity: type in `kg` or `sticks` — Cash↔Qty calculator auto-converts.
4. Customer: leave as default Retail (cashier locked to Retail group).
5. Click **PAY**.
6. Tender modes:
   - **Cash** (default mode): cashier types received amount.
     - If overage rounding is needed (e.g., ₦2,000 cash for ₦1,980 sale), the
       system auto-adds a **Round Off** GL entry of ₦20 credit.
     - `change_amount` remains 0 to avoid double-booking.
   - **Transfer** (POS-Incoming): customer pays into outlet bank account.
   - **Card / POS Terminal**: same flow as Transfer.
7. Click **Submit**. Receipt prints on Sungas Thermal 58mm format.

### Receipt format

The thermal receipt includes:
- Sungas logo + brand
- Per-outlet address (auto-pulled from Branch)
- Item lines (Item | Qty | Rate | Amount)
- Subtotal, Round Off, Grand Total
- Cash received / Outstanding
- **Code 128 barcode** encoding `<INVOICE_NUMBER>|<TOTAL_QTY>` for handover scanning
- T&C footer + VERVEFLAME promo

> If receipt is blank / generic format, see Troubleshooting Runbook §1.

## C) Closing Shift — Cashier

1. At end of shift, click **Close Shift** in POS Awesome.
2. The system shows you:
   - Expected closing cash = opening + cash sales − cash refunds
   - List of all transactions in this shift (POS Invoice rows)
3. Physically count the cash in the till.
4. Enter **Closing Cash Balance** (actual physical count).
5. Review:
   - **Difference Amount** = actual − expected
   - Negative = short; Positive = over
6. Add a note explaining any variance (e.g., "Lost ₦200 in dispute").
7. Click **Submit Close** → status becomes `Closing` (pending Plant Mgr approval).

> The shift cannot be re-opened once submitted. If you discover the count was
> wrong, ask the Plant Manager to cancel + redo.

## D) Approving Close & Reconciliation — Plant Manager

1. Open `Selling > POS Closing Shift > List`.
2. Find today's shift (status = `Closing`).
3. Review difference. Threshold guidance:
   - **₦0 to ±₦200**: tolerated, approve directly
   - **±₦201 to ±₦2,000**: investigate cause (customer dispute, mistype)
   - **> ±₦2,000**: escalate to Head of Finance, may trigger Loss Adjustment GL
4. Click **Submit** to approve. POS Invoice consolidation runs automatically.
5. The system creates one consolidated `Sales Invoice` per payment mode.

> **Note**: POS Closing Shift is in **POS Invoice mode** (not Sales Invoice).
> Auto-consolidation runs at close to roll up individual invoices into a
> single Sales Invoice per tender per shift. This was configured during Phase 5.5.

### Post-close GL flow (automatic)

```
POS Invoice → consolidated Sales Invoice
  ├── Cash collected      Dr  Cash - <Outlet>
  ├── Transfer collected  Dr  POS-Incoming - <Outlet>
  ├── Card collected      Dr  POS-Incoming - <Outlet>
  └── Round Off variance  Cr  Round Off Account
                         Cr  Sales LPG / Cylinder Sales (revenue)
                         Cr  VAT (if applicable)
```

> Cost centers: auto-routed to outlet `XX002 - Sales and Marketing` CC.

## E) Daily Reconciliation — Finance / Head of Finance

Next morning workflow:

1. Open `Accounts > Bank Reconciliation Statement`.
2. For each outlet:
   - Match POS-Incoming Dr to bank credit (Transfer/Card collections).
   - Cash Dr should match cash deposit slip (cash pickup vendor or daily bank lodgement).
3. Investigate unmatched lines via `POS Closing Shift > Cashier name` filter.
4. If shortage > ₦2,000, raise variance under `Stock Entry > Type=Material Issue`
   against Loss Adjustment account.

## Permission summary

| Doctype | Cashier | Plant Mgr | HoF |
|---|---|---|---|
| POS Opening Shift | Create | Read | Read |
| POS Closing Shift | Create | Submit / Cancel | Read |
| POS Invoice | Create / Read own | Read all | Read all |
| Customer (Retail group) | Create only — locked by Server Script | Read+Write | Full |
| Customer (Bulk/Wholesale) | (denied) | Read | Full |
| Item Price | (none) | Read | (none) |
| Sales Invoice (consolidated) | (none) | Read | Submit / Cancel |

## Bench scripts (for IT reference)

| Script | Use when |
|---|---|
| `scripts/phase5_smoke_test.py` | After any POS Awesome update — runs 27-case regression |
| `scripts/clone_pos_profiles_to_outlets.py` | New outlet rollout |
| `scripts/lockdown_pos_profile.py` | Strip default customer if cashier complains |
| `scripts/diagnose_pos_setup.py` | "Why won't POS open" debugging |
| `scripts/fix_customer_lockdown.py` | Re-deploy customer lockdown Server Scripts |

## Quick troubleshooting

| Symptom | First action |
|---|---|
| Cashier sees no items in POS grid | Check POS Profile > Item Groups + warehouse stock filter |
| Cart shows ₦0 unit price | Confirm price list `SCL Standard Selling` + tier present for customer-territory |
| "Sale blocked — no tier" toast | LPG strict mode; HoS must seed price tier for that warehouse |
| Receipt prints generic format | Print Format > `Sungas Thermal 58mm` > Custom Format flag must = 1 |
| Customer dropdown shows Bulk | Server Script `Sungas - Force Retail Group On Customer Insert` not firing |

See [08. Troubleshooting Runbook](./08-troubleshooting-runbook.md) for deeper dives.
