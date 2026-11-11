// posa-0020: rows priced below unit cost are shown red; Submit is blocked server-side.
const posa_mark_below_cost = (frm) => {
	const grid = frm.fields_dict.rows && frm.fields_dict.rows.grid;
	(grid ? grid.grid_rows : []).forEach((gr) => {
		const below = gr.doc.flag_status === "Below Cost";
		$(gr.row)
			.css({ "background-color": below ? "#fff5f5" : "", color: below ? "#c53030" : "" })
			.attr("title", below ? __("Below unit cost by {0}", [format_currency(gr.doc.cost_gap, gr.doc.currency)]) : "");
	});
};

frappe.ui.form.on("LPG Bulk Price Upload", {
	refresh(frm) {
		setTimeout(() => posa_mark_below_cost(frm), 300);
	},
});
