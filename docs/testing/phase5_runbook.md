# Phase 5 — POS Awesome Tester's Runbook

Smoke test for the 6 customizations deployed to `sungasmis.v.frappe.cloud`.

| # | Feature | How |
|---|---------|-----|
| 1 | Tiered pricing | Automated (script) |
| 2 | ₦ ↔ Kg auto-calc | **Manual UI** (this doc) |
| 3 | Barcode receipt | **Manual UI** (this doc) |
| 4 | Price-change workflow | Automated (script) |
| 5 | Mobile uniqueness | Automated (script) |
| 6 | Phone/name search | Automated (script) |

---

## Part A — Automated backend tests (Features 1, 4, 5, 6)

### Step 1 — Upload the script

The smoke-test script lives in this repo at `scripts/phase5_smoke_test.py`.
Get it onto the bench server:

```bash
# from your laptop, or via Frappe Cloud "Bench Shell"
cd /home/frappe/frappe-bench       # or your bench path
curl -L -o /tmp/phase5_smoke_test.py \
  https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/develop/scripts/phase5_smoke_test.py
```

(Or just paste the file contents into `/tmp/phase5_smoke_test.py` via `nano`.)

### Step 2 — Run it

```bash
bench --site sungasmis.v.frappe.cloud execute \
  "exec(open('/tmp/phase5_smoke_test.py').read())"
```

### Step 3 — Read the summary

A PASS/FAIL table is printed at the end. **All rows should be PASS.**
The script:
- creates fixtures prefixed `SMK-` (test Item, Customer Group, Territory, Customer, Tier, PCR),
- exercises each feature,
- deletes everything it created.

If any row fails, share the **full console output** back to me.

---

## Part B — Manual UI tests (Features 2, 3)

Run these as a user with **Sales Manager** + **LPG POS User** roles on a POS Profile.

### Feature 2 — ₦ ↔ Kg auto-calculator

**Pre-req**: pick an Item where **Item.weight_uom = "Kg"** and **weight_per_unit > 0**.
For sungas this is typically `LPG-REFILL` (1 Kg/unit) or `LPG-12KG` (12 Kg/unit).

**Steps**:

1. Open **POS Awesome** for any cashier.
2. Select a customer (e.g. `Cosmic` or any test customer).
3. Add an `LPG-12KG` item to the cart.
4. In the cart, find the **Kg Qty** and **Rate / Kg** columns (or fields in the item editor sidebar).
5. **Test A — qty drives kg**: change Qty to `2` → expect Kg Qty = `24.000`.
6. **Test B — kg drives qty**: change Kg Qty to `36` → expect Qty = `3`.
7. **Test C — rate drives rate/kg**: change Rate to `36 000` → expect Rate/Kg = `3000.000000`.
8. **Test D — rate/kg drives rate**: change Rate/Kg to `2 500` → expect Rate = `30 000`.
9. Click **Save** (draft) → in the desk Sales Invoice, the row should show the same `posa_kg_qty` and `posa_rate_per_kg`.

**Pass criteria**: all 4 directions sync, no NaN, no flicker.

**Known**: for items where `weight_uom ≠ "Kg"` or `weight_per_unit = 0`, the Kg fields stay at **0** — that's intentional (opt-in per item).

### Feature 3 — Barcode receipt

**Steps**:

1. In POS Awesome, complete a sale (any customer, any item, submit).
2. After submit, the receipt print preview opens.
3. **Test A — barcode renders**: a Code128 barcode appears under the Invoice No.
4. **Test B — barcode encodes `{invoice_name}|{total_kg}`**:
   - The text below the barcode should read e.g. `ACC-SINV-2026-00042|24.00`.
5. **Test C — barcode scans back**: scan it with any phone Code128 scanner app → it returns the same string.
6. **Test D — desk form has the field**: open the submitted Sales Invoice in desk → field `posa_receipt_barcode` (Data, read-only) shows the same payload.

**Pass criteria**: barcode renders on print, payload matches `<invoice>|<total_kg>`, scans correctly.

**Print-format note**: if barcode renders as plain text instead of bars, the active Print Format isn't using `{{ get_barcode_image(doc.posa_receipt_barcode) }}`. Edit the Print Format and add an HTML block with that Jinja call.

---

## Part C — What "all green" means

When Part A prints `Failed: 0` **and** Part B's 8 manual checks all pass, Phase-5 is functionally signed off.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `Workflow 'LPG Price Change Approval' not found` | `bench --site sungasmis.v.frappe.cloud migrate` (re-runs `after_migrate`). |
| `5c FAIL — second insert was allowed` | The `Customer.validate` hook isn't wired. Check `hooks.py` `doc_events.Customer.validate`. |
| `1c FAIL — row.rate not overridden` | `apply_tiered_pricing` isn't in `doc_events.Sales Invoice.validate`. Check `posawesome.posawesome.api.invoice.validate` calls it. |
| `6a FAIL — no hits` | The test customer's `mobile_no` didn't get canonicalized; check `enforce_unique_mobile` hook. |
| Kg fields stay 0 in POS | The item's `weight_uom` isn't `Kg` or `weight_per_unit` is 0. Open the Item and set both. |
| Barcode prints as text | Print Format Jinja missing `{{ get_barcode_image(doc.posa_receipt_barcode) }}`. |
