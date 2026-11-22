# Feature: Stock Available Now at the till (posa-0048)

**Status:** Built — awaiting deploy (needs Sungas patches 0067 + 0068 for the server check at receipt save)
**Tracking:** Sungas — overselling across channels

## Why

A till receipt (POS Invoice) moves no stock until the till closes. The till tiles and the quantity limit
("Block sale beyond available qty", on for every Sungas till) used the recorded stock only, so a plant with
1,000 kg recorded and 900 kg already sold that day still showed 1,000 kg and let the cashier sell it again.

## What changed

**Available now = recorded stock − till sales (not returns) not yet closed into a Sales Invoice**, in stock units (kg).

| Call site | File | Used by |
|---|---|---|
| `open_till_qty(warehouses, item_codes)` | `posawesome/posawesome/api/item_fetchers.py` | shared query (POS Invoice Items + Packed Items, `docstatus = 1`, `is_return = 0`, not consolidated) |
| `_fetch_bin_qty` | `item_fetchers.py` | item tiles (`actual_qty`) |
| `get_stock_availability` | `posawesome/posawesome/api/items.py` | item detail / `get_available_qty` (quantity limit) |
| `get_bulk_stock_availability` | `items.py` | bulk refresh of the cart |

No front-end change: after each receipt the till already deducts the sold kg locally (`stockCoordinator.applyInvoiceConsumption`);
the next server read subtracts the same receipt, so nothing is counted twice.

## Back-office side (Sungas app)

- **0068** — server check when the receipt is saved (two tills selling the last kg at once wait for each other):
  *"Not enough LPG Refill: 100 available now (1,000 recorded less 900 sold today and not yet closed). Reduce the quantity."*
  Receipts made offline and sent more than 10 minutes later are not blocked (the sale has happened).
- **0067** — the same figure on Delivery Notes, stock-moving Sales Invoices and Stock Entries; till close stops with a clear
  message and alerts the Plant Manager + Finance if recorded stock cannot cover the shift; report *Stock Available Now*.

## Test

`/app/backend/tests/test_posa_0048_available_now.py`, `/app/backend/tests/test_sungas_0067_stock_available.py`.
