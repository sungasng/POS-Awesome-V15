/**
 * POS Awesome — LPG Tier Pricing (Client-Side Notice)
 * --------------------------------------------------------------
 * Shows a non-intrusive banner the moment a cashier picks an item
 * with an applicable LPG Outlet Price Tier, so they can announce
 * the correct rate to the customer BEFORE save.
 *
 * Why a banner instead of mutating the rate field?
 *   ERPNext's `get_item_details` + pricing pipeline aggressively
 *   refetches the price-list rate every time `rate`, `qty`, or
 *   `item_code` changes. Fighting it with `frappe.model.set_value`
 *   creates a feedback loop that ends with rate=0.
 *
 *   The server-side validate hook (apply_tiered_pricing) overrides
 *   the rate on save with 100% reliability — proven by the bench
 *   diagnostic (server: rate=3000, amount=37500).
 *
 *   So the only UX gap is "what does the cashier SEE before save?"
 *   This banner closes that gap without touching the form state.
 *
 * Banner content:
 *   "Tier price applies: <tier_name> -> N3,000 per unit
 *    (current display N1,360 is the standard price-list rate;
 *    final invoice will use the tier rate)."
 */

(function () {
        const TIER_CACHE = {};

        function fetchTier(itemCode, customer, qty) {
                if (!itemCode || !customer) return Promise.resolve(null);
                const key = `${itemCode}|${customer}|${qty || 0}`;
                if (TIER_CACHE[key]) return Promise.resolve(TIER_CACHE[key]);
                return frappe
                        .call({
                                method: "posawesome.posawesome.api.lpg_pricing.get_tier_rate",
                                args: { item_code: itemCode, customer, qty: qty || 0 },
                                freeze: false,
                        })
                        .then((r) => {
                                const data = (r && r.message) || null;
                                if (data) TIER_CACHE[key] = data;
                                return data;
                        });
        }

        function bannerEl(frm) {
                // Reuse a single banner div per form instance.
                let el = frm.$wrapper.find(".posa-tier-banner");
                if (el.length === 0) {
                        el = $(
                                '<div class="posa-tier-banner alert alert-info" ' +
                                        'style="margin: 8px 0; display: none; ' +
                                        'border-left: 4px solid #2196f3; ' +
                                        'background: #e3f2fd; color: #0d47a1; ' +
                                        'padding: 10px 16px; font-size: 14px;">' +
                                        "</div>",
                        );
                        // Insert above the Items grid.
                        const itemsField = frm.fields_dict.items;
                        if (itemsField && itemsField.$wrapper) {
                                el.insertBefore(itemsField.$wrapper);
                        } else {
                                frm.$wrapper.find(".form-section").first().prepend(el);
                        }
                }
                return el;
        }

        function refreshBanner(frm) {
                const el = bannerEl(frm);
                if (!frm.doc.customer || !frm.doc.items || !frm.doc.items.length) {
                        el.hide().empty();
                        return;
                }

                // Collect tier info for every row in parallel.
                const promises = frm.doc.items.map((row) =>
                        fetchTier(row.item_code, frm.doc.customer, row.qty || 1).then((info) => ({
                                row,
                                info,
                        })),
                );

                Promise.all(promises).then((results) => {
                        const tiered = results.filter((r) => r.info && r.info.has_tier);
                        if (tiered.length === 0) {
                                el.hide().empty();
                                return;
                        }

                        const lines = tiered.map(({ row, info }) => {
                                const tierRate = Number(info.rate || 0);
                                const currentRate = Number(row.rate || 0);
                                const tierFmt = `₦${tierRate.toLocaleString("en-NG")}`;
                                const currentFmt = `₦${currentRate.toLocaleString("en-NG")}`;
                                const same = Math.abs(tierRate - currentRate) < 0.005;
                                if (same) {
                                        return (
                                                `<div><b>${frappe.utils.escape_html(row.item_code)}</b>: ` +
                                                `tier price <b>${tierFmt}</b> applied ` +
                                                `<small>(${frappe.utils.escape_html(info.tier_name)})</small></div>`
                                        );
                                }
                                return (
                                        `<div><b>${frappe.utils.escape_html(row.item_code)}</b>: ` +
                                        `tier price will be <b>${tierFmt}</b> on save ` +
                                        `<small>(showing ${currentFmt} = standard price list. ` +
                                        `Tier: ${frappe.utils.escape_html(info.tier_name)})</small></div>`
                                );
                        });

                        el.html(
                                '<div style="font-weight: 600; margin-bottom: 4px;">' +
                                        __("LPG tier pricing in effect for this customer:") +
                                        "</div>" +
                                        lines.join(""),
                        ).show();
                });
        }

        // Throttle so we don't spam the API while user types qty.
        let throttleTimer = null;
        function scheduleRefresh(frm) {
                if (throttleTimer) clearTimeout(throttleTimer);
                throttleTimer = setTimeout(() => refreshBanner(frm), 300);
        }

        const FORM_HANDLERS = {
                customer: scheduleRefresh,
                refresh: scheduleRefresh,
                items_add: scheduleRefresh,
                items_remove: scheduleRefresh,
        };

        const ROW_HANDLERS = {
                item_code: function (frm) {
                        scheduleRefresh(frm);
                },
                qty: function (frm) {
                        scheduleRefresh(frm);
                },
        };

        ["Sales Invoice", "POS Invoice", "Quotation", "Sales Order"].forEach((parentDt) => {
                frappe.ui.form.on(parentDt, FORM_HANDLERS);
        });
        ["Sales Invoice Item", "POS Invoice Item", "Quotation Item", "Sales Order Item"].forEach(
                (childDt) => {
                        frappe.ui.form.on(childDt, ROW_HANDLERS);
                },
        );
})();
