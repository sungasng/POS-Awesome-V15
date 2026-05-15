// Copyright (c) 20201 Youssef Restom and contributors
// For license information, please see license.txt

frappe.ui.form.on("Sales Invoice", {
	setup: function (frm) {
		frm.set_query("posa_delivery_charges", function (doc) {
			return {
				filters: { company: doc.company, disabled: 0 },
			};
		});
	},
});

// Phase-5 Feature: ₦ ↔ Kg amount-due calculator (desk Sales Invoice form)
// When the cashier types into "Amount Due (₦)" on a child row, drive qty
// from amount / rate so totals update reactively (same UX as POS Awesome).
frappe.ui.form.on("Sales Invoice Item", {
	posa_amount_due: function (frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row) return;
		const rate = flt(row.rate);
		const amount_due = flt(row.posa_amount_due);
		if (rate <= 0 || amount_due <= 0) return;

		const expected = flt(rate * flt(row.qty), 2);
		if (Math.abs(amount_due - expected) < 0.01) return; // no real change

		// Round DOWN qty to 1 decimal (Sungas dispenser precision).
		const new_qty = Math.floor((amount_due / rate) * 10) / 10;
		if (new_qty === flt(row.qty)) return;
		if (new_qty <= 0) return;

		frappe.model.set_value(cdt, cdn, "qty", new_qty);
	},
});
