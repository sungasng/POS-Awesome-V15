# 06 — Stock Adjustment & Reconciliation

Physical count vs system count, variance investigation, write-off procedure.

## When to use

- **Daily**: cylinder count at outlet (typically 7am, before opening)
- **Weekly**: bulk LPG dipstick reading vs system Qty
- **Monthly**: full physical inventory for accounting close
- **Ad-hoc**: after suspicious shortage / overage > ±5%

## Roles

| Role | Responsibility |
|---|---|
| **Stores Officer** | Performs physical count |
| **Plant Manager** | Records adjustment in ERP |
| **Head of Finance** | Approves write-off > ₦50,000 |
| **Internal Control** | Audits adjustments monthly |

## Process — Stock Reconciliation

The cleanest tool for adjusting on-hand Qty is `Stock Reconciliation`.

### Step-by-step (Plant Manager)

1. `Stock > Stock Reconciliation > New`.
2. **Purpose**: "Opening Stock" or "Stock Reconciliation".
3. **Posting Date / Time**: backdated to count time.
4. Click **Get Items** with filter:
   - Warehouse: `Apapa Cylinders - SCL`
   - Item Group: e.g., "Cylinders"
5. System fills the table with current `Quantity` + `Current Valuation Rate`.
6. Enter the physical count in `Quantity` column.
7. The system computes `Difference Amount` per row.
8. If only some items have variance, delete rows with `Quantity Difference = 0`.
9. Add note: reason for variance.
10. **Submit**.

> The system generates a Material Receipt or Material Issue Stock Entry
> behind the scenes to balance the book.

## Variance thresholds

| Variance | Action |
|---|---|
| ≤ ±0.5% of stock | Tolerated, log and submit |
| ±0.5% – ±2% | Plant Manager investigates, documents in note |
| ±2% – ±5% | Escalate to Head of Operations |
| > ±5% | Escalate to Internal Control + Head of Finance; suspend cashier shift if pattern emerges |

## GL impact of adjustment

Variance posts to **Stock Adjustment** account:

```
If Qty went UP (gain):
  Inventory Dr
  Stock Adjustment Cr   (other income or gain)

If Qty went DOWN (loss):
  Stock Adjustment Dr   (expense)
  Inventory Cr
```

> Default `Stock Adjustment Account` is set on the Company.
> Verify via: `Company > Sungas Company Limited > Stock Adjustment Account`.

## Difference between Stock Entry (Material Issue) vs Stock Reconciliation

| Tool | When | Why |
|---|---|---|
| Material Issue | Known loss event (drop, theft, damage) | Specific expense account |
| Stock Reconciliation | Periodic count vs system | Catch-all variance to one account |

Use Material Issue when the **cause is known and traceable**.
Use Stock Reconciliation when you just need to **align book to physical**.

## LPG bulk reconciliation (special case)

LPG kg in tank can drift due to:
- Temperature & vapour pressure
- Tanker offload measurement error
- Filling spillage / fitting loss

Process:
1. Stores Officer takes dipstick reading.
2. Convert to kg using outlet's tank calibration table.
3. If variance < 1% of tank capacity → log, no adjustment.
4. If 1–3% → adjust via Stock Reconciliation, note "Operational shrinkage".
5. If > 3% → Plant Manager investigates valve / leak; involves maintenance.

## Audit trail

Every Stock Reconciliation:
- Submission creates linked Stock Entry (visible via "Connections")
- Cannot be edited post-submit; only cancelled + re-done
- `Version` doctype records the changes
- Stock Ledger shows pre/post Qty + linked SR document name

## Common errors

| Error | Cause | Fix |
|---|---|---|
| "Stock cannot be updated against the closed Period" | Year-end close | Run pre-close-date or after open |
| "Valuation rate is required for item" | New item with no rate | Set `Valuation Rate` on Item or in SR row |
| Negative Qty appears after SR | Backdated entry conflicts with later movements | Re-sequence or use Repost Item Valuation |
| "Item is stock item" but row blank | Item flagged stock but no qty/rate entered | Either fix row or delete row |

## Monthly close checklist

End of every month:

- [ ] All cashier shifts closed by end-of-day on last day
- [ ] Empty cylinder count reconciled per outlet
- [ ] LPG bulk dipstick reading recorded per outlet
- [ ] Stock Reconciliation submitted per warehouse
- [ ] Stock Adjustment GL line < 2% of inventory value (else investigate)
- [ ] Internal Control signs off via comment on each SR

## Bench scripts (reference)

- `scripts/stock_audit_report.py` — generates per-outlet variance report (custom)
- `scripts/repost_item_valuation.py` — fix valuation drift after backdated entries
