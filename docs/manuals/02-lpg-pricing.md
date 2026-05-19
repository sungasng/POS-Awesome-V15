# 02 — LPG Pricing

How to change LPG sell rates across one plant, a region, or all outlets.

## Roles

| Role | Access |
|---|---|
| **Head of Sales & Marketing** (`LPG Head of Sales`) | Full read/write on Item Price |
| **Plant Manager** (`LPG Plant Manager`) | Read-only on Item Price |

## Pricing Architecture (Sungas custom)

LPG pricing is governed by the **LPG Outlet Price Tier** doctype (custom), which
stacks on top of standard ERPNext `Item Price`:

```
LPG Outlet Price Tier
  ├── warehouse  (= outlet, e.g., "Pedro - SCL")
  ├── territory  (= customer group region, e.g., "Pedro")
  ├── customer_group  (Retail / Bulk / Wholesale)
  └── rate        (₦/kg)

Resolved at sale time:
  if (cart.warehouse, cart.customer.territory, cart.customer.group) in tiers:
      use tier rate
  else:
      throw "No tier — sale blocked" (strict mode)
```

> The `posawesome` backend (`api/items.py` → `apply_tiers_to_rows`) is the
> single source of truth. The customer arg MUST be passed in frontend calls.

## Workflow — Change LPG Price

### Scope 1: Single Plant

Use when: Outlet-specific promo (e.g., "Pedro ₦1,350/kg this weekend").

1. Open `Selling > LPG Outlet Price Tier > List`.
2. Filter `warehouse = <Outlet> - SCL`.
3. Find the row for the target customer group (usually Retail).
4. Click row → change `rate`.
5. **Save**. New rate is live on next cart calculation (no cache).

### Scope 2: Region (multiple outlets sharing a territory)

Use when: Lagos-wide price change (e.g., Pedro + Ikeja + Oshodi + Ebute).

**Preferred**: Script-driven (atomic, audit trail):

1. Edit `/scripts/seed_all_lpg_tier_rates.py` — change the matrix dict.
2. Push to `feat/sungas-customizations`.
3. Plant IT to run:
   ```bash
   curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/feat/sungas-customizations/scripts/seed_all_lpg_tier_rates.py" -o /tmp/seed.py
   bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/seed.py').read())"
   ```
4. Script is **idempotent**: existing rows unchanged → updated; new rows → created.

**Alternative**: Manual via UI — repeat Scope 1 for each outlet (slow, error-prone).

### Scope 3: Whole Company

Use when: National tariff change (e.g., NLNG quote moved, all outlets up ₦20/kg).

1. Same script approach as Scope 2 — edit the full matrix.
2. Run on bench.
3. Verify via report: `Selling > Item Price > Group by warehouse`.

> The 64-row matrix in `seed_all_lpg_tier_rates.py` covers all 21 outlets ×
> 4 customer groups. Editing it is the safest production-grade approach.

## Tier matrix structure (reference)

| Outlet | Retail (₦/kg) | Bulk (₦/kg) | Wholesale (₦/kg) | Reseller (₦/kg) |
|---|---:|---:|---:|---:|
| Pedro | 1,360 | 1,340 | 1,320 | 1,310 |
| Asaba | 1,365 | 1,345 | 1,325 | 1,315 |
| Eleme | 1,380 | 1,360 | 1,340 | 1,330 |
| ... (all 21 outlets) | ... | ... | ... | ... |

Edit only the cells that change — script preserves the rest.

## Validation post-change

1. Open POS Awesome at a sample outlet.
2. Add 1kg LPG to cart for a Retail customer.
3. Confirm cart shows the new rate.
4. Add 1kg for a Bulk customer (need to switch to Sales Invoice mode since Bulk
   isn't on POS) — confirm new Bulk rate.

If POS shows old rate after a change:
- Hot-fix the cache via `bench --site sungasmis.v.frappe.cloud clear-cache`.
- Hard reload the POS browser tab.

## Non-tiered items

LPG cylinders and accessories don't go through the tier system. See
[03. Non-LPG Pricing](./03-non-lpg-pricing.md).

## GL impact

Changing the price changes the unit rate on **future** POS Invoices only.
Already-submitted invoices are untouched (auditable). No backdating.

Revenue posts to:
- `Sales LPG - <Outlet>` (e.g., `Sales LPG - Pedro`)
- Cost Center: outlet `XX002 - Sales and Marketing`

## Common errors

| Error | Cause | Fix |
|---|---|---|
| "Sale blocked — no tier" toast | Tier missing for outlet × territory × group combo | Add the row to `seed_all_lpg_tier_rates.py` and run |
| Cart shows ₦0 | Tier present but rate = 0 | Set non-zero rate |
| Old rate cached at POS | Frontend cache | `bench clear-cache` + browser hard reload |
| Tier rate applied to wrong territory | Customer.territory mismatched | Fix customer's territory field |

## Audit trail

Every Item Price edit / LPG Outlet Price Tier edit is logged in:
- `Version` doctype (per-record diff)
- Activity log (per-user)

Pull report: `Reports > Item Price > group by modified_by, modified`.
