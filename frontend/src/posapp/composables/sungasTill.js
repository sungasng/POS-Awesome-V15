// Sungas posa-0047: cashiers get the simple till view; managers keep everything.
const MANAGERS = ["LPG Plant Manager", "LPG Head of Operations", "LPG Head of Finance", "System Manager"];

export const isSimpleTill = () =>
	typeof frappe !== "undefined" &&
	frappe.user?.has_role?.("LPG POS User") &&
	!MANAGERS.some((r) => frappe.user.has_role(r));
