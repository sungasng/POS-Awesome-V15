/**
 * POS Awesome — LPG Tier Pricing (Client-Side)
 * --------------------------------------------------------------
 * Auto-applies the LPG Outlet Price Tier rate the instant the cashier
 * picks an item or changes the customer — BEFORE save.
 *
 * Eliminates the "announced wrong rate" UX bug where rate jumps from
 * price-list value to tier value only after Save.
 *
 * Also locks the rate field for tier-managed rows (defense in depth)
 * so a cashier cannot manually override a board-approved price.
 *
 * Wired in hooks.py:
 *     doctype_js = {
 *         "Sales Invoice": "...",
 *         "Quotation": "...",
 *         "Sales Order": "...",
 *     }
 */

(function () {
        // Cache: { "item|customer|qty": {has_tier, rate, tier_name} }
        const TIER_CACHE = {};

        function cacheKey(item, customer, qty) {
                return `${item || ""}|${customer || ""}|${qty || 0}`;
        }

        function fetchTier(itemCode, customer, qty) {
                if (!itemCode || !customer) return Promise.resolve(null);
                const key = cacheKey(itemCode, customer, qty);
                if (TIER_CACHE[key]) return Promise.resolve(TIER_CACHE[key]);
                return frappe
                        .call({
                                method: "posawesome.posawesome.api.lpg_pricing.get_tier_rate",
                                args: {
                                        item_code: itemCode,
                                        customer,
                                        qty: qty || 0,
                                },
                                freeze: false,
                        })
                        .then((r) => {
                                const data = (r && r.message) || null;
                                if (data) TIER_CACHE[key] = data;
                                return data;
                        });
        }

        function applyTierToRow(frm, row) {
                if (!row || !row.item_code || !frm.doc.customer) return;
                const qty = flt(row.qty) || 1;
                fetchTier(row.item_code, frm.doc.customer, qty).then((info) => {
                        if (!info || !info.has_tier) return;
                        const tierRate = flt(info.rate);
                        if (!tierRate) return;

                        if (flt(row.rate) === tierRate) {
                                // Already at tier rate — just ensure lock state.
                                lockRateField(frm, row);
                                return;
                        }

                        // Delay our write until ERPNext's get_item_details / pricing
                        // pipeline has finished. Without the delay our set_value
                        // arrives BEFORE ERPNext's price_list_rate handler, which
                        // then clobbers our tier rate. 250 ms is conservative for
                        // the typical Frappe async chain (~50-150 ms).
                        setTimeout(() => {
                                // Re-read the row in case the user already changed item_code again.
                                const live = locals[row.doctype] && locals[row.doctype][row.name];
                                if (!live || live.item_code !== row.item_code) return;

                                frappe.model.set_value(row.doctype, row.name, "price_list_rate", tierRate);
                                frappe.model
                                        .set_value(row.doctype, row.name, "rate", tierRate)
                                        .then(() => {
                                                const existing = live.posa_offers || "";
                                                const marker = `LPG-Tier:${info.tier_name}`;
                                                if (!existing.includes(marker)) {
                                                        frappe.model.set_value(
                                                                row.doctype,
                                                                row.name,
                                                                "posa_offers",
                                                                (existing + "," + marker).replace(/^,+|,+$/g, ""),
                                                        );
                                                }
                                                lockRateField(frm, row);
                                                frappe.show_alert(
                                                        {
                                                                message: __("LPG tier rate applied: {0} → ₦{1}", [
                                                                        info.tier_name,
                                                                        tierRate.toLocaleString("en-NG"),
                                                                ]),
                                                                indicator: "blue",
                                                        },
                                                        4,
                                                );
                                        });
                        }, 250);
                });
        }

        function lockRateField(frm, row) {
                // Make the rate cell read-only at the row level.
                // The grid API only exposes per-column toggle, so we set the
                // row-level read_only flag on the field via the grid_row API.
                try {
                        const grid = frm.fields_dict.items && frm.fields_dict.items.grid;
                        if (!grid) return;
                        const gridRow = grid.grid_rows_by_docname[row.name];
                        if (!gridRow) return;
                        ["rate", "price_list_rate"].forEach((fname) => {
                                if (gridRow.docfields) {
                                        gridRow.docfields.forEach((df) => {
                                                if (df.fieldname === fname) {
                                                        df.read_only = 1;
                                                }
                                        });
                                }
                        });
                        gridRow.refresh_field && gridRow.refresh_field("rate");
                        gridRow.refresh_field && gridRow.refresh_field("price_list_rate");
                } catch (e) {
                        // Non-fatal — if locking fails the server-side validate still enforces tier.
                        console.warn("[lpg_tier] could not lock rate field:", e);
                }
        }

        function applyTierToAllRows(frm) {
                if (!frm || !frm.doc || !frm.doc.customer) return;
                (frm.doc.items || []).forEach((row) => applyTierToRow(frm, row));
        }

        const FORM_HANDLERS = {
                customer: function (frm) {
                        // Re-check every row when customer changes (different group/territory).
                        applyTierToAllRows(frm);
                },
                refresh: function (frm) {
                        // On reopen of a saved doc, re-lock tier-managed rows.
                        applyTierToAllRows(frm);
                },
        };

        const ROW_HANDLERS = {
                item_code: function (frm, cdt, cdn) {
                        applyTierToRow(frm, locals[cdt][cdn]);
                },
                qty: function (frm, cdt, cdn) {
                        // Qty can shift which tier bracket applies (e.g. 50+ kg → bulk tier).
                        applyTierToRow(frm, locals[cdt][cdn]);
                },
                // After ERPNext's pricing pipeline updates price_list_rate, our
                // earlier set_value may have been clobbered. Re-apply tier rate here.
                price_list_rate: function (frm, cdt, cdn) {
                        applyTierToRow(frm, locals[cdt][cdn]);
                },
                rate: function (frm, cdt, cdn) {
                        // Last line of defense — if anything (user typing, pricing rule,
                        // get_item_details) drops the rate off the tier value, re-pin it.
                        applyTierToRow(frm, locals[cdt][cdn]);
                },
        };

        // Wire up the same handlers on all four sales doctypes.
        ["Sales Invoice", "POS Invoice", "Quotation", "Sales Order"].forEach((parentDt) => {
                frappe.ui.form.on(parentDt, FORM_HANDLERS);
        });
        ["Sales Invoice Item", "POS Invoice Item", "Quotation Item", "Sales Order Item"].forEach(
                (childDt) => {
                        frappe.ui.form.on(childDt, ROW_HANDLERS);
                },
        );
})();
