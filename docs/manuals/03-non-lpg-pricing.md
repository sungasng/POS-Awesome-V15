# 03 — Non-LPG Pricing (Cylinders, Accessories, Hoses, Burners)

How to change non-LPG item rates across one plant, a region, or all outlets.

## Roles

| Role | Access |
|---|---|
| **Head of Sales & Marketing** | Full read/write on Item Price |
| **Plant Manager** | Read-only on Item Price |

## Pricing Architecture

Non-LPG items use **standard ERPNext `Item Price`** (NOT the LPG tier system).

```
Item Price
  ├── item_code      (e.g., "CYL-3KG")
  ├── price_list     ("SCL Standard Selling")
  ├── customer / customer_group  (optional — usually blank for universal price)
  ├── selling = 1
  └── price_list_rate  (₦)

Resolved at sale time:
  ERPNext picks the best-match Item Price row:
    1. Customer-specific match
    2. Customer Group match
    3. Generic (no customer)
```

## Workflow — Change Non-LPG Price

### Scope 1: Single Plant

Use when: Outlet has unique freight cost (rare for cylinders).

> Most cylinders/accessories use a **single national price** (`SCL Standard Selling`).
> Per-outlet pricing for non-LPG is uncommon.

If genuinely outlet-specific:

1. Create a separate `Price List` per outlet (e.g., "Pedro Selling").
2. Set POS Profile `selling_price_list` to that list.
3. Add Item Prices under that list.

### Scope 2: Region

For regional differences (e.g., southwest 3kg cylinder is ₦12,500; southeast is ₦12,800):

1. Use Item Price + filter by Customer Group.
2. e.g., Customer Group = "Retail SW" gets ₦12,500; "Retail SE" gets ₦12,800.
3. Requires customer.customer_group to be set correctly.

Better long-term: Per-outlet price lists (script via `scripts/set_outlet_price_list.py`).

### Scope 3: Whole Company

The default — single national price per non-LPG item.

#### Procedure (HoS)

1. Open `Selling > Item Price > List`.
2. Filter `price_list = SCL Standard Selling` AND `item_code = <ITEM>`.
3. Click the row → update `price_list_rate`.
4. **Save**.
5. The new price is live immediately on POS / Sales Invoice / Quotation.

#### Bulk change via script (preferred for >5 items)

Use `scripts/set_non_lpg_prices.py` (template). Example payload:

```python
NON_LPG_PRICES = {
    "CYL-3KG":   12500,
    "CYL-6KG":   18500,
    "CYL-12.5KG":35000,
    "BURNER-2H":  6500,
    "HOSE-1M":    1200,
}
```

Then:
```bash
curl -fsSL "<raw url>/scripts/set_non_lpg_prices.py" -o /tmp/np.py
bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/np.py').read())"
```

> Script idempotent: updates existing rate if changed, inserts new row otherwise.

## Validation

1. Open POS at any outlet.
2. Search "3kg" / "Burner" — confirm new price displays.
3. Add to cart → confirm `Rate` matches new price.
4. PAY → submit → reopen invoice → confirm GL hit `Sales Cylinder - <Outlet>`.

## GL impact

Non-LPG sales post to dedicated income accounts:

| Item category | GL Account |
|---|---|
| Cylinders (3kg/6kg/12.5kg/25kg/50kg) | `Sales Cylinder - <Outlet>` |
| Accessories (hose, regulator, burner) | `Sales Accessories - <Outlet>` |
| Punitive / Replacement parts | `Sales Other - <Outlet>` |

> Item Group → Income Account mapping is set in `Item Default` table on each Item.
> If new items don't post correctly, check `Item > Default Income Account` per outlet.

## Common errors

| Error | Cause | Fix |
|---|---|---|
| Item Price update doesn't reflect at POS | Cache | `bench clear-cache` + browser reload |
| Cart shows different price than Item Price | Customer-specific price overrides generic | Check `Item Price > Customer` field |
| New item not in POS | `is_pos_item=0` or item group not in POS Profile | Set `is_pos_item=1`, ensure group included |
| Item Price says "Multiple price for same item" warning | Duplicate Item Price rows | Delete duplicates; keep the most recent |

## Audit trail

Same as LPG — `Version` doctype + Activity log.
HoS edits are visible to Head of Finance for audit.

## Permissions

| Action | Role required |
|---|---|
| Change Item Price | `LPG Head of Sales` or `Item Manager` |
| Create new Item | `Item Manager` only |
| View Item Price | Plant Manager + above |
