# 05 — Stock Entry (Receipts & Transfers)

How LPG and cylinders enter / move through Sungas warehouses.

> **No workflow approval** is configured for Stock Entry — submission is direct.
> Plant Managers and Stores Officers can submit immediately. (Reconciliation
> happens via Stock Adjustment — see [06](./06-stock-adjustment.md).)

## Roles

| Role | What they do |
|---|---|
| **Stores Officer** | Daily depot intake (LPG tanker offloading, cylinder pallets) |
| **Plant Manager** | Approves / verifies; transfers between sub-warehouses |
| **Head of Finance** | Reviews stock value GL impact via Stock Ledger Report |

## Warehouse Structure

```
Apapa - SCL                          (parent — outlet root)
  ├── Apapa LPG Tank - SCL           (bulk LPG storage)
  ├── Apapa Cylinders - SCL          (filled cylinders + accessories)
  └── Apapa Returned Empties - SCL   (returned cylinders awaiting refill)
```

Each outlet follows the same 3-warehouse pattern.

## Stock Entry Types

ERPNext has 5 Stock Entry types — Sungas uses 3:

| Type | When | Affects |
|---|---|---|
| **Material Receipt** | LPG truck arrives, cylinders delivered ex-factory | + In-stock |
| **Material Transfer** | LPG bulk → cylinders filled; or outlet-to-outlet | Source - / Target + |
| **Material Issue** | Variance, damage write-off | - From stock |

## A) Daily Depot Intake — Stores Officer

### LPG Tanker Receipt

1. Open `Stock > Stock Entry > New`.
2. Type: **Material Receipt**.
3. Date/time: now.
4. Items table:
   - Item: `LPG-REFILL` (LPG bulk in kg)
   - Qty: weight ticket reading (kg)
   - **Target warehouse**: `Apapa LPG Tank - SCL`
   - Basic Rate: cost per kg from supplier invoice (e.g., ₦1,100/kg)
5. Add to footer:
   - Supplier invoice no.: e.g. "NLNG-INV-202601-0089"
   - Tanker plate: e.g. "LAG-456-XY"
   - Weight ticket: attach scan
6. **Submit**.

> GL impact: Inventory Dr ₦X / Stock In-Hand Cr ₦X (auto via Item Valuation).

### Cylinder Receipt

Same as above, but:
- Item: `CYL-3KG` / `CYL-6KG` / `CYL-12.5KG` etc.
- Qty: count
- Target: `Apapa Cylinders - SCL`

### Accessory Receipt

- Item: `BURNER-2H`, `HOSE-1M`, `REGULATOR-STD`
- Target: `Apapa Cylinders - SCL`

## B) Filling Operation — Plant Manager

When LPG moves from bulk tank to cylinders being filled for retail:

1. `Stock > Stock Entry > New`.
2. Type: **Material Transfer**.
3. Items:
   | From Warehouse | To Warehouse | Item | Qty |
   |---|---|---|---|
   | Apapa LPG Tank | Apapa Cylinders | LPG-REFILL | (kg filled) |

> This is the daily fill operation. Records gas as moving from bulk to retail-ready.

## C) Outlet-to-Outlet Transfer — Plant Manager

When cylinders move between outlets (e.g., Pedro overstocked, Apapa understocked):

1. `Stock > Stock Entry > New`.
2. Type: **Material Transfer**.
3. From Warehouse: `Pedro Cylinders - SCL`
4. To Warehouse: `Apapa Cylinders - SCL`
5. Items: e.g., 50× `CYL-6KG`
6. Add field `purpose` = "Stock balancing"
7. **Submit**.

> GL impact: zero (transfers between accounts of the same Company don't post GL).

## D) Returned Empties Handling — Stores Officer

When a customer returns an empty cylinder:

1. POS Invoice itself does **NOT** track empty returns automatically.
2. At day end, count returned empties.
3. `Stock > Stock Entry > Material Receipt`:
   - Item: `CYL-6KG-EMPTY` (sub-item — or use a custom field on the parent item)
   - Qty: count
   - Target: `Apapa Returned Empties - SCL`
   - Rate: 0 (empties are valuation-neutral)

> Long-term recommendation: configure `posawesome` to auto-record empties.
> Currently a manual step.

## E) Damage / Loss — Plant Manager

Cylinder dropped, hose punctured:

1. `Stock > Stock Entry > Material Issue`.
2. From Warehouse: source warehouse.
3. Item + qty.
4. **Expense account**: `Loss on Stock - <Outlet> - SCL`.
5. Note: reason + photo.
6. **Submit**.

> GL impact: Loss on Stock Dr / Inventory Cr.

## Permissions

| Doctype | Stores Officer | Plant Mgr | HoF |
|---|---|---|---|
| Stock Entry (Material Receipt) | Create + Submit | Create + Submit | Read |
| Stock Entry (Material Transfer) | Create | Create + Submit | Read |
| Stock Entry (Material Issue) | (denied) | Create + Submit | Submit only with note |
| Stock Reconciliation | (denied) | Create + Submit | Approve |
| Stock Ledger | Read all | Read all | Read all |

## Common Errors

| Error | Cause | Fix |
|---|---|---|
| "Negative stock not allowed" | Issuing more than current Qty | Receive more or run Stock Reconciliation |
| "Item is stock item but warehouse missing" | Item flagged `is_stock_item=1` but no warehouse on row | Set Target Warehouse |
| Stock Entry doesn't post GL | Item Group `Default Income Account` missing | Set on Item Group |
| Transfer between outlets blocks due to "Stock Closure" | Year-end close in progress | Wait for closure to complete or run after |

## Reports to verify

- `Stock > Stock Balance` — current Qty per warehouse
- `Stock > Stock Ledger` — every movement, timestamped
- `Accounts > Stock In-Hand` — book value per warehouse
- `Stock > Stock Receipt Note` — supplier-side delivery log
