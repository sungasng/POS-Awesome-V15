# Sungas ERPNext v15 — Operational Manuals

Comprehensive how-to and reference documentation for day-to-day operations on
the Sungas ERPNext v15 stack (Frappe Cloud bench `sungasmis.v.frappe.cloud`).

## Audience guide

| Manual | Primary reader | When to use |
|---|---|---|
| [01. POS Shift Operations](./01-pos-shift-operations.md) | Cashier + Plant Manager | Every business day |
| [02. LPG Pricing](./02-lpg-pricing.md) | Head of Sales & Marketing | When tariff changes |
| [03. Non-LPG Pricing](./03-non-lpg-pricing.md) | Head of Sales & Marketing | Cylinder/accessory cost moves |
| [04. New Outlet Setup](./04-new-outlet-setup.md) | IT/Sysadmin + Finance/HR | Outlet rollout (target: 1–2/yr) |
| [05. Stock Entry (Receipts)](./05-stock-entry.md) | Stores Officer | LPG depot intake, restocks |
| [06. Stock Adjustment](./06-stock-adjustment.md) | Plant Manager + Stores | Variance reconciliation |
| [07. Top 10 Reports](./07-top-10-reports.md) | All managers | Daily/weekly review |
| [08. Troubleshooting Runbook](./08-troubleshooting-runbook.md) | IT / power user | Bug or anomaly |
| [09. Architecture & Data Dictionary](./09-architecture-data-dictionary.md) | IT / new dev onboarding | Reference |
| [10. Disaster Recovery](./10-disaster-recovery.md) | IT lead | Outage / data loss |

## Conventions used across manuals

- **Path notation**: `Module > Doctype > Action` — e.g., `Selling > Item Price > New`
- **Code blocks** with `bash` are run on the Frappe Cloud bench (SSH).
- **Permissions**: Role names refer to ERPNext Role Profiles set up for Sungas
  (`LPG POS User`, `LPG Plant Manager`, `LPG Head of Sales`, `LPG Head of Finance`).
- **Custom apps** referenced: `posawesome`, `sungas`, `hr_enhancements`.

## Versioning

Last updated: 2026-05-19 (Phase 6 / HRMS configuration).
Docs live in `/docs/manuals/` on branch `feat/sungas-customizations`.
Submit edits via Pull Request — DO NOT edit in production.
