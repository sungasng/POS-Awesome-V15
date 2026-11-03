// Copyright (c) 2026, Sungas — POS Awesome customization
/* global frappe, __ */
frappe.query_reports["LPG Tier Resolver Diagnostic"] = {
  filters: [
    {
      fieldname: "item_code",
      label: __("Item"),
      fieldtype: "Link",
      options: "Item",
      reqd: 1,
    },
    {
      fieldname: "customer_group",
      label: __("Customer Group"),
      fieldtype: "Link",
      options: "Customer Group",
      reqd: 1,
    },
    {
      fieldname: "territory",
      label: __("Outlet / Territory"),
      fieldtype: "Link",
      options: "Territory",
      description: __(
        "Leaf outlet to simulate (Pedro, Ekehuan, etc.). Leave blank to test global / empty-territory tiers only."
      ),
    },
    {
      fieldname: "qty",
      label: __("Qty"),
      fieldtype: "Float",
      default: 1,
    },
    {
      fieldname: "posting_date",
      label: __("Posting Date"),
      fieldtype: "Date",
      default: frappe.datetime.get_today(),
    },
  ],
};
