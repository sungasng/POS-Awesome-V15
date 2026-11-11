# Copyright (c) 2026, Sungas — POS Awesome customization
# For license information, see license.txt
"""
LPG Bulk Price Upload (Pricing Wave B — P-3).

A submittable batch of LPG Outlet Price Tier changes.

Lifecycle (per user direction, 2026-02-20)::

    Draft
      └─(Submit, LPG Head of Sales)──▶ Pending Head of Finance
                                          ├─(Approve, LPG Head of Finance)──▶ Approved
                                          │                                      │
                                          │                                      ▼
                                          │                          on_submit: upsert tiers
                                          │
                                          └─(Reject,  LPG Head of Finance)──▶ Rejected

Single approval level: Head of Finance. There is no CFO tier.

Governance (`Sungas Pricing Policy`):
    - `bulk_upload_change_flag_pct` (default 15%) → |Δ| above this marks
      the row as Flagged AND requires non-empty justification.
    - `bulk_upload_change_block_pct` (default 30%) — retained on the
      policy doctype for dashboard / KPI use, **but no longer triggers
      any workflow branching**. Head of Finance sees the row delta and
      decides on Approve/Reject alone.

The Consultation Record requirement was explicitly removed per user
direction (Pricing-B, 2026-02-20).
"""

from __future__ import annotations

import csv
import io
import os

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, get_files_path, get_site_path, now, today

# Reuse the production resolver so "current_rate" reflects exactly what the
# POS would charge today (walk-up + safety valve).
from posawesome.posawesome.api.lpg_pricing import find_applicable_tier


_CSV_HEADER = (
    "item_code",
    "customer_group",
    "territory",
    "min_qty",
    "max_qty",
    "new_rate",
    "valid_from",
    "valid_to",
    "justification",
)


class LPGBulkPriceUpload(Document):
    # ------------------------------------------------------------------
    # Hooks
    # ------------------------------------------------------------------
    def validate(self):
        self._stamp_meta()
        self._maybe_parse_csv()
        self._enrich_rows()
        self._apply_governance()
        self._track_approval_stamps()
        self._refresh_summary()

    def on_submit(self):
        # The Frappe workflow only sets doc_status=1 on the Approved state,
        # so any submit reaching here is implicitly the approved one. Guard
        # anyway in case a System Manager bypasses the workflow.
        if (self.workflow_state or "").strip() != "Approved":
            frappe.throw(_("Cannot submit a bulk upload that is not Approved."))
        self._upsert_tiers()

    # ------------------------------------------------------------------
    # Step 1 — meta stamps
    # ------------------------------------------------------------------
    def _stamp_meta(self) -> None:
        if self.is_new():
            if not self.uploader:
                self.uploader = frappe.session.user
            if not self.upload_date:
                self.upload_date = now()

    # ------------------------------------------------------------------
    # Step 2 — optional CSV auto-parse
    # ------------------------------------------------------------------
    def _maybe_parse_csv(self) -> None:
        """If a source file is attached and the rows table is empty, parse
        the CSV into rows. CSV parsing is deliberately pure-Python (no
        openpyxl dep) so the tests stay hermetic.
        """
        if self.rows:
            return
        if not self.upload_source_file:
            return

        path = _resolve_file_path(self.upload_source_file)
        if not path or not os.path.exists(path):
            self.parse_status = "Source file not found on disk"
            return

        try:
            with open(path, "r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                missing = [h for h in _CSV_HEADER if h not in (reader.fieldnames or [])]
                # `justification` and `valid_from/to` are optional; only
                # the first 4 columns are strictly required.
                strict = {"item_code", "customer_group", "new_rate"}
                missing_required = strict.intersection(missing)
                if missing_required:
                    self.parse_status = "Missing required header(s): " + ", ".join(
                        sorted(missing_required)
                    )
                    return

                parsed = 0
                for raw in reader:
                    if not (raw.get("item_code") or "").strip():
                        continue
                    self.append("rows", {
                        "item_code": (raw.get("item_code") or "").strip(),
                        "customer_group": (raw.get("customer_group") or "").strip() or None,
                        "territory": (raw.get("territory") or "").strip() or None,
                        "min_qty": flt(raw.get("min_qty") or 0),
                        "max_qty": flt(raw.get("max_qty") or 0),
                        "new_rate": flt(raw.get("new_rate") or 0),
                        "valid_from": (raw.get("valid_from") or "").strip() or None,
                        "valid_to": (raw.get("valid_to") or "").strip() or None,
                        "justification": (raw.get("justification") or "").strip() or None,
                        "enabled": 1,
                    })
                    parsed += 1
            self.parse_status = f"Parsed {parsed} row(s) from CSV"
        except Exception as exc:  # pragma: no cover — surfaced to UI
            self.parse_status = f"Parse failed: {exc}"

    # ------------------------------------------------------------------
    # Step 3 — enrich rows with current rate + % change
    # ------------------------------------------------------------------
    def _enrich_rows(self) -> None:
        posting_date = today()
        for row in (self.rows or []):
            tier = find_applicable_tier(
                item_code=row.item_code,
                customer_group=row.customer_group,
                territory=row.territory,
                qty=flt(row.min_qty or 0),
                posting_date=posting_date,
            )
            row.current_rate = flt(tier.get("rate")) if tier else 0
            new = flt(row.new_rate or 0)
            if row.current_rate and row.current_rate != 0:
                row.pct_change = (new - row.current_rate) * 100.0 / row.current_rate
            else:
                # No existing tier — treat as 100% delta so policy still triggers
                # whenever the user introduces a price out of the blue. The
                # justification requirement keeps brand-new SKU pricing honest.
                row.pct_change = 100.0 if new > 0 else 0.0

    # ------------------------------------------------------------------
    # Step 4 — apply policy thresholds
    # ------------------------------------------------------------------
    def _apply_governance(self) -> None:
        flag_pct, _block_pct = _read_thresholds()
        missing: list[str] = []
        for idx, row in enumerate(self.rows or [], start=1):
            mag = abs(flt(row.pct_change or 0))
            if flag_pct and mag > flag_pct:
                row.flag_status = "Flagged"
            else:
                row.flag_status = "OK"
            if row.flag_status == "Flagged" and not (row.justification or "").strip():
                missing.append(
                    f"  Row {idx} ({row.item_code} @ {row.territory or 'N/A'}): "
                    f"|Δ|={mag:.2f}% needs justification."
                )
        self._mark_below_cost()
        if missing:
            frappe.throw(
                _(
                    "Justification is mandatory for the following flagged row(s):\n{lines}"
                ).format(lines="\n".join(missing)),
                title=_("Justification Required"),
            )

    # Patch posa-0020: below-cost rows save (marked, with cost + gap) but cannot leave Draft.
    def _mark_below_cost(self) -> None:
        from posawesome.posawesome.api.lpg_pricing_guards import item_unit_cost
        below = []
        for idx, row in enumerate(self.rows or [], start=1):
            cost = item_unit_cost(row.item_code) if row.item_code else None
            row.unit_cost = flt(cost)
            row.cost_gap = 0
            if cost is not None and flt(row.new_rate) < cost:
                row.flag_status = "Below Cost"
                row.cost_gap = flt(cost - flt(row.new_rate), 2)
                below.append(f"Row {idx} {row.item_code}: NGN {flt(row.new_rate):,.2f} is NGN "
                             f"{row.cost_gap:,.2f} below unit cost NGN {cost:,.2f}")
        if below and (self.workflow_state or "Draft") not in ("Draft", "Rejected"):
            frappe.throw(
                _("Fix or remove the rows marked Below Cost before submitting:<br>{0}<br><br>"
                  "To sell below cost, Finance must first write the stock down to net realisable value "
                  "(Stock Reconciliation, valuation only, approved by Head of Finance).").format("<br>".join(below)),
                title=_("Below Cost Price"))

    # ------------------------------------------------------------------
    # Step 5 — workflow approval stamps
    # ------------------------------------------------------------------
    def _track_approval_stamps(self) -> None:
        before = self.get_doc_before_save()
        old_state = before.workflow_state if before else None
        new_state = self.workflow_state
        if old_state == new_state:
            return
        if new_state == "Approved" and (old_state or "") == "Pending Head of Finance":
            self.approved_by_finance = frappe.session.user
            self.finance_approved_on = now()

    # ------------------------------------------------------------------
    # Step 6 — summary aggregates
    # ------------------------------------------------------------------
    def _refresh_summary(self) -> None:
        total = len(self.rows or [])
        flagged = sum(1 for r in (self.rows or []) if r.flag_status == "Flagged")
        max_pct = max((abs(flt(r.pct_change or 0)) for r in (self.rows or [])), default=0.0)
        self.total_rows = total
        self.flagged_rows = flagged
        self.max_pct_change = max_pct

    # ------------------------------------------------------------------
    # Step 8 — upsert resolved tiers (called from on_submit)
    # ------------------------------------------------------------------
    def _upsert_tiers(self) -> None:
        log: list[str] = []
        for row in (self.rows or []):
            if not cint(row.enabled):
                log.append(f"- {row.item_code}: skipped (disabled flag).")
                continue
            existing = frappe.db.get_value(
                "LPG Outlet Price Tier",
                {
                    "item_code": row.item_code,
                    "customer_group": row.customer_group,
                    "territory": row.territory,
                    "min_qty": row.min_qty or 0,
                },
                "name",
            )
            if existing:
                tier = frappe.get_doc("LPG Outlet Price Tier", existing)
                tier.rate = row.new_rate
                tier.max_qty = row.max_qty or 0
                tier.valid_from = row.valid_from
                tier.valid_to = row.valid_to
                tier.currency = row.currency or tier.currency or "NGN"
                tier.enabled = 1
                tier.notes = (
                    (tier.notes or "")
                    + f"\nUpdated by Bulk Upload {self.name} on {now()} "
                    + f"(was {row.current_rate}, justification: {row.justification or '-'})"
                ).strip()
                tier.save(ignore_permissions=True)
                action = "updated"
            else:
                tier = frappe.get_doc({
                    "doctype": "LPG Outlet Price Tier",
                    "item_code": row.item_code,
                    "customer_group": row.customer_group,
                    "territory": row.territory,
                    "min_qty": row.min_qty or 0,
                    "max_qty": row.max_qty or 0,
                    "rate": row.new_rate,
                    "currency": row.currency or "NGN",
                    "valid_from": row.valid_from,
                    "valid_to": row.valid_to,
                    "enabled": 1,
                    "notes": (
                        f"Created by Bulk Upload {self.name} on {now()} "
                        f"(justification: {row.justification or '-'})"
                    ),
                })
                tier.insert(ignore_permissions=True)
                action = "created"

            row.db_set("created_tier", tier.name, update_modified=False)
            log.append(
                f"- {row.item_code} | {row.customer_group} | "
                f"{row.territory or 'GLOBAL'} | {row.min_qty or 0}: "
                f"{action} {tier.name} @ {row.new_rate} "
                f"(was {row.current_rate}, Δ={row.pct_change:.2f}%)"
            )

        self.db_set("created_tiers", "\n".join(log) or "(no rows applied)")


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def _resolve_file_path(file_url: str | None) -> str | None:
    """Translate a Frappe File URL (`/files/x.csv` or
    `/private/files/x.csv`) to an absolute disk path.
    """
    if not file_url:
        return None
    if file_url.startswith("/private/files/"):
        return os.path.join(get_files_path(is_private=1), file_url.split("/private/files/", 1)[1])
    if file_url.startswith("/files/"):
        return os.path.join(get_files_path(), file_url.split("/files/", 1)[1])
    if file_url.startswith("/"):
        return os.path.join(get_site_path(), file_url.lstrip("/"))
    return file_url


def _read_thresholds() -> tuple[float, float]:
    """Return (flag_pct, block_pct) from Sungas Pricing Policy. Defaults
    mirror the doctype defaults (15% / 30%).
    """
    flag_pct, block_pct = 15.0, 30.0
    try:
        if frappe.db.exists("DocType", "Sungas Pricing Policy"):
            flag_pct = flt(
                frappe.db.get_single_value("Sungas Pricing Policy", "bulk_upload_change_flag_pct")
                or 15.0
            )
            block_pct = flt(
                frappe.db.get_single_value("Sungas Pricing Policy", "bulk_upload_change_block_pct")
                or 30.0
            )
    except Exception:
        pass
    return flag_pct, block_pct


# ----------------------------------------------------------------------
# Pure helper used by tests (no document required)
# ----------------------------------------------------------------------

def classify_pct_change(pct: float, flag_pct: float, block_pct: float = 0) -> str:
    """
    Classify a row's % change against governance thresholds.

    Post 2026-02-20: there is no CFO tier. The function preserves the
    `block_pct` parameter for backward compatibility (older callers and
    KPI dashboards) but treats anything above `flag_pct` as "Flagged".
    `block_pct` itself is intentionally ignored for the workflow path.
    """
    mag = abs(flt(pct))
    if flag_pct and mag > flag_pct:
        return "Flagged"
    return "OK"


def parse_csv_text(text: str) -> tuple[list[dict], str]:
    """Parse CSV text into row dicts. Returns (rows, status_message).
    Exposed so unit tests can drive it without a Frappe File on disk.
    """
    reader = csv.DictReader(io.StringIO(text))
    missing = [h for h in ("item_code", "customer_group", "new_rate")
               if h not in (reader.fieldnames or [])]
    if missing:
        return [], "Missing required header(s): " + ", ".join(missing)
    parsed: list[dict] = []
    for raw in reader:
        if not (raw.get("item_code") or "").strip():
            continue
        parsed.append({
            "item_code": (raw.get("item_code") or "").strip(),
            "customer_group": (raw.get("customer_group") or "").strip() or None,
            "territory": (raw.get("territory") or "").strip() or None,
            "min_qty": flt(raw.get("min_qty") or 0),
            "max_qty": flt(raw.get("max_qty") or 0),
            "new_rate": flt(raw.get("new_rate") or 0),
            "valid_from": (raw.get("valid_from") or "").strip() or None,
            "valid_to": (raw.get("valid_to") or "").strip() or None,
            "justification": (raw.get("justification") or "").strip() or None,
        })
    return parsed, f"Parsed {len(parsed)} row(s) from CSV"
