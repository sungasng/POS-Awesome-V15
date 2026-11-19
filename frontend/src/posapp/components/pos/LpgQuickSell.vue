<template>
	<!-- Sungas posa-0045/0047: LPG refill pad. Tap a size = full refill; Part fill + size = kg or naira into that cylinder. -->
	<div class="lpg-quick" data-testid="lpg-quick-sell">
		<span class="lpg-quick-label">{{ __("LPG refill") }}</span>
		<v-btn
			size="small"
			:variant="part ? 'flat' : 'outlined'"
			:color="part ? 'warning' : 'secondary'"
			class="lpg-quick-btn"
			data-testid="lpg-quick-part-fill"
			@click="part = !part"
			>{{ part ? __("Part fill: ON") : __("Part fill") }}</v-btn
		>
		<v-btn
			v-for="s in sizes"
			:key="s"
			size="small"
			:variant="part ? 'outlined' : 'tonal'"
			color="primary"
			class="lpg-quick-btn"
			:data-testid="`lpg-quick-${String(s).replace('.', '-')}kg`"
			@click="tap(s)"
			>{{ s }} kg</v-btn
		>
	</div>
</template>

<script>
export default {
	name: "LpgQuickSell",
	emits: ["pick"],
	data: () => ({ sizes: [3, 6, 7, 10, 12.5, 15, 18, 20, 25, 50], part: false }),
	methods: {
		tap(size) {
			const uom = `${size}kg Cyl`;
			if (!this.part) {
				this.$emit("pick", { uom });
				return;
			}
			const d = frappe.prompt(
				[
					{ fieldname: "kg", fieldtype: "Float", label: __("Kg to fill") },
					{ fieldname: "cb", fieldtype: "Column Break" },
					{ fieldname: "amount", fieldtype: "Currency", label: __("or Amount the customer pays (₦)") },
				],
				(v) => {
					if (!(v.kg > 0) && !(v.amount > 0)) {
						frappe.msgprint(__("Enter the kg or the amount."));
						return;
					}
					this.part = false;
					this.$emit("pick", v.kg > 0 ? { fill_into: uom, kg: v.kg } : { fill_into: uom, amount: v.amount });
				},
				__("Part fill into a {0} kg cylinder", [size]),
				__("Add"),
			);
			d.$wrapper.css("z-index", 3000);
		},
	},
};
</script>

<style scoped>
.lpg-quick {
	display: flex;
	flex-wrap: wrap;
	align-items: center;
	gap: 6px;
	padding: 4px 12px 8px;
}
.lpg-quick-label {
	font-size: 13px;
	font-weight: 600;
	margin-right: 4px;
}
.lpg-quick-btn {
	min-width: 52px;
	font-weight: 600;
	text-transform: none;
}
</style>
