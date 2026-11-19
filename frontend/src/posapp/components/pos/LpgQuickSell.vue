<template>
	<!-- Sungas posa-0045: one tap adds a cylinder refill; or sell LPG by naira amount. -->
	<div class="lpg-quick" data-testid="lpg-quick-sell">
		<span class="lpg-quick-label">{{ __("LPG refill") }}</span>
		<v-btn
			v-for="s in sizes"
			:key="s"
			size="small"
			variant="tonal"
			color="primary"
			class="lpg-quick-btn"
			:data-testid="`lpg-quick-${String(s).replace('.', '-')}kg`"
			@click="$emit('pick', { uom: `${s}kg Cyl` })"
			>{{ s }} kg</v-btn
		>
		<v-btn
			size="small"
			variant="flat"
			color="primary"
			class="lpg-quick-btn"
			data-testid="lpg-quick-amount"
			@click="askAmount"
			>{{ __("By ₦ amount") }}</v-btn
		>
	</div>
</template>

<script>
export default {
	name: "LpgQuickSell",
	emits: ["pick"],
	data: () => ({ sizes: [3, 6, 12.5, 25, 50] }),
	methods: {
		askAmount() {
			frappe.prompt(
				[{ fieldname: "amount", fieldtype: "Currency", label: __("Amount the customer is paying (₦)"), reqd: 1 }],
				(v) => v.amount > 0 && this.$emit("pick", { amount: v.amount }),
				__("Sell LPG by amount"),
				__("Add"),
			);
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
	min-width: 56px;
	font-weight: 600;
	text-transform: none;
}
</style>
