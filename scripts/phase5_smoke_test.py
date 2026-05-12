"""
Phase-5 backend smoke test for POS Awesome (sungas).

Validates the 4 backend-heavy features:
    1. Tiered pricing  (LPG Outlet Price Tier override on Sales Invoice)
    4. Price-change approval workflow (3-stage approval -> auto-creates tier)
    5. Customer mobile normalization + uniqueness
    6. Phone/name search API

Run on Frappe Cloud bench:
    cd ~/frappe-bench
    bench --site sungasmis.v.frappe.cloud execute \
        "exec(open('/tmp/phase5_smoke_test.py').read())"

Idempotent. Creates docs prefixed `SMK-` / `PCR-SMK-` and deletes them on exit.
Prints a PASS/FAIL summary table at the end.
"""

from __future__ import annotations

import sys
import traceback

import frappe
from frappe.utils import flt, today

# ---------------------------------------------------------------------------
# Test fixtures (created on demand, torn down at end)
# ---------------------------------------------------------------------------
TEST_PREFIX = "SMK"
TEST_CUSTOMER = f"{TEST_PREFIX} Test Customer"
TEST_CUSTOMER_DUP = f"{TEST_PREFIX} Test Customer Dup"
TEST_GROUP = f"{TEST_PREFIX}-Group"
TEST_TERRITORY = f"{TEST_PREFIX}-Territory"
TEST_ITEM = f"{TEST_PREFIX}-LPG-12KG"
TEST_RAW_PHONE = "08031234567"
TEST_CANONICAL_PHONE = "2348031234567"
TIER_RATE = 3000.0
STANDARD_RATE = 1360.0
TIER_NAME_HINT = f"TIER-{TEST_ITEM}-{TEST_GROUP}-{TEST_TERRITORY}-0"

RESULTS: list[tuple[str, bool, str]] = []


def _record(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    flag = "PASS" if ok else "FAIL"
    print(f"  [{flag}] {name}" + (f"  --  {detail}" if detail else ""))


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------
def _ensure_customer_group():
    if not frappe.db.exists("Customer Group", TEST_GROUP):
        parent = (
            "All Customer Groups"
            if frappe.db.exists("Customer Group", "All Customer Groups")
            else frappe.db.get_value("Customer Group", {"is_group": 1}, "name")
        )
        frappe.get_doc({
            "doctype": "Customer Group",
            "customer_group_name": TEST_GROUP,
            "parent_customer_group": parent,
            "is_group": 0,
        }).insert(ignore_permissions=True)


def _ensure_territory():
    if not frappe.db.exists("Territory", TEST_TERRITORY):
        parent = (
            "All Territories"
            if frappe.db.exists("Territory", "All Territories")
            else frappe.db.get_value("Territory", {"is_group": 1}, "name")
        )
        frappe.get_doc({
            "doctype": "Territory",
            "territory_name": TEST_TERRITORY,
            "parent_territory": parent,
            "is_group": 0,
        }).insert(ignore_permissions=True)


def _ensure_item():
    if not frappe.db.exists("Item", TEST_ITEM):
        item_group = frappe.db.get_value("Item Group", {"is_group": 0}, "name") or "All Item Groups"
        frappe.get_doc({
            "doctype": "Item",
            "item_code": TEST_ITEM,
            "item_name": "SMK 12Kg Test Cylinder",
            "item_group": item_group,
            "stock_uom": "Nos",
            "is_stock_item": 0,
            "weight_per_unit": 12,
            "weight_uom": "Kg",
        }).insert(ignore_permissions=True)


def _ensure_customer(name: str, mobile: str | None = None):
    if frappe.db.exists("Customer", name):
        return frappe.get_doc("Customer", name)
    doc = frappe.get_doc({
        "doctype": "Customer",
        "customer_name": name,
        "customer_group": TEST_GROUP,
        "territory": TEST_TERRITORY,
        "customer_type": "Individual",
        "mobile_no": mobile or "",
    }).insert(ignore_permissions=True)
    return doc


def _ensure_tier():
    """Create a tier (TIER_RATE) for (TEST_ITEM, TEST_GROUP, TEST_TERRITORY)."""
    existing = frappe.db.get_value(
        "LPG Outlet Price Tier",
        {
            "item_code": TEST_ITEM,
            "customer_group": TEST_GROUP,
            "territory": TEST_TERRITORY,
            "min_qty": 0,
        },
        "name",
    )
    if existing:
        tier = frappe.get_doc("LPG Outlet Price Tier", existing)
        tier.rate = TIER_RATE
        tier.enabled = 1
        tier.save(ignore_permissions=True)
        return tier
    return frappe.get_doc({
        "doctype": "LPG Outlet Price Tier",
        "item_code": TEST_ITEM,
        "customer_group": TEST_GROUP,
        "territory": TEST_TERRITORY,
        "min_qty": 0,
        "max_qty": 0,
        "rate": TIER_RATE,
        "currency": "NGN",
        "enabled": 1,
        "notes": "Created by phase5_smoke_test.py",
    }).insert(ignore_permissions=True)


# ---------------------------------------------------------------------------
# Feature 1 — Tiered pricing override on Sales Invoice
# ---------------------------------------------------------------------------
def test_feature_1_tiered_pricing():
    print("\n[1] Tiered Pricing override")
    _ensure_customer_group()
    _ensure_territory()
    _ensure_item()
    customer = _ensure_customer(TEST_CUSTOMER, TEST_RAW_PHONE)
    _ensure_tier()

    # Direct API check first
    from posawesome.posawesome.api.lpg_pricing import find_applicable_tier, get_tier_rate
    found = find_applicable_tier(
        item_code=TEST_ITEM,
        customer_group=TEST_GROUP,
        territory=TEST_TERRITORY,
        qty=1,
        posting_date=today(),
    )
    _record(
        "1a find_applicable_tier returns matching tier",
        bool(found) and flt(found.get("rate")) == TIER_RATE,
        f"got rate={found.get('rate') if found else None}",
    )

    api_resp = get_tier_rate(TEST_ITEM, customer.name, 1, today())
    _record(
        "1b get_tier_rate API returns has_tier + rate",
        api_resp.get("has_tier") is True and flt(api_resp.get("rate")) == TIER_RATE,
        f"resp={api_resp}",
    )

    # Build a draft Sales Invoice, set a deliberately-wrong rate, and verify
    # apply_tiered_pricing hook overrides it on validate.
    si = frappe.new_doc("Sales Invoice")
    si.customer = customer.name
    si.posting_date = today()
    si.due_date = today()
    si.set_posting_time = 1
    si.append("items", {
        "item_code": TEST_ITEM,
        "qty": 1,
        "rate": STANDARD_RATE,           # deliberately wrong
        "price_list_rate": STANDARD_RATE,
        "uom": "Nos",
        "conversion_factor": 1,
    })
    si.flags.ignore_mandatory = True
    si.flags.ignore_permissions = True
    try:
        si.run_method("validate")
        row = si.items[0]
        _record(
            "1c Sales Invoice row rate overridden to tier rate",
            flt(row.rate) == TIER_RATE,
            f"row.rate={row.rate} expected={TIER_RATE}",
        )
        _record(
            "1d Sales Invoice row amount uses tier rate",
            flt(row.amount) == TIER_RATE * flt(row.qty),
            f"row.amount={row.amount}",
        )
    except Exception as e:
        _record("1c Sales Invoice validate", False, f"exception: {e}")


# ---------------------------------------------------------------------------
# Feature 4 — Price Change Workflow (3-stage approval)
# ---------------------------------------------------------------------------
def _ensure_workflow_test_users():
    """Make sure the 4 LPG workflow roles exist on Administrator for testing."""
    admin = frappe.get_doc("User", "Administrator")
    needed = ("LPG Plant Manager", "LPG Head of Sales", "LPG Head of Finance")
    have = {r.role for r in admin.roles}
    changed = False
    for r in needed:
        if r not in have and frappe.db.exists("Role", r):
            admin.append("roles", {"role": r})
            changed = True
    if changed:
        admin.save(ignore_permissions=True)


def test_feature_4_workflow():
    print("\n[4] Price-change approval workflow")
    _ensure_customer_group()
    _ensure_territory()
    _ensure_item()
    _ensure_workflow_test_users()

    if not frappe.db.exists("Workflow", "LPG Price Change Approval"):
        _record(
            "4 Workflow installed", False,
            "Workflow 'LPG Price Change Approval' not found. "
            "Run: bench --site <site> migrate (after_migrate hook installs it)."
        )
        return

    # Clean up any prior smoke-test PCRs
    for n in frappe.get_all(
        "LPG Price Change Request",
        filters={"reason": ["like", "SMK smoke test%"]},
        pluck="name",
    ):
        try:
            doc = frappe.get_doc("LPG Price Change Request", n)
            if doc.docstatus == 1:
                doc.cancel()
            frappe.delete_doc("LPG Price Change Request", n, force=1, ignore_permissions=True)
        except Exception:
            pass

    pcr = frappe.get_doc({
        "doctype": "LPG Price Change Request",
        "item_code": TEST_ITEM,
        "customer_group": TEST_GROUP,
        "territory": TEST_TERRITORY,
        "proposed_rate": 3500,
        "min_qty": 0,
        "max_qty": 0,
        "reason": "SMK smoke test — auto-generated PCR",
        "workflow_state": "Pending Plant Manager",
    }).insert(ignore_permissions=True)
    _record("4a PCR created", bool(pcr.name), f"name={pcr.name}")

    from frappe.model.workflow import apply_workflow
    try:
        pcr = apply_workflow(pcr, "Approve")  # Plant Mgr -> HoS
        pcr = apply_workflow(pcr, "Approve")  # HoS -> HoF
        pcr = apply_workflow(pcr, "Approve")  # HoF -> Approved
        pcr.reload()
    except Exception as e:
        _record("4b 3-stage Approve transitions", False, f"exception: {e}")
        return

    _record(
        "4b workflow_state == Approved",
        pcr.workflow_state == "Approved",
        f"state={pcr.workflow_state}",
    )
    _record(
        "4c docstatus == 1 (Submitted)",
        pcr.docstatus == 1,
        f"docstatus={pcr.docstatus}",
    )
    _record(
        "4d created_tier link populated",
        bool(pcr.created_tier),
        f"created_tier={pcr.created_tier}",
    )

    if pcr.created_tier and frappe.db.exists("LPG Outlet Price Tier", pcr.created_tier):
        tier_rate = flt(frappe.db.get_value("LPG Outlet Price Tier", pcr.created_tier, "rate"))
        _record(
            "4e new tier rate == proposed_rate",
            tier_rate == 3500.0,
            f"tier_rate={tier_rate}",
        )

    _record(
        "4f plant_manager / head_of_sales / head_of_finance stamps recorded",
        bool(pcr.plant_manager) and bool(pcr.head_of_sales) and bool(pcr.head_of_finance),
        f"pm={pcr.plant_manager} hos={pcr.head_of_sales} hof={pcr.head_of_finance}",
    )


# ---------------------------------------------------------------------------
# Feature 5 — Mobile uniqueness + canonicalization
# ---------------------------------------------------------------------------
def test_feature_5_mobile():
    print("\n[5] Customer mobile normalization + uniqueness")
    from posawesome.posawesome.api.customer_mobile import normalize_mobile

    # Unit cases
    cases = [
        ("+234 803 123 4567", "2348031234567"),
        ("08031234567",       "2348031234567"),
        ("8031234567",        "2348031234567"),
        ("234-803-123-4567",  "2348031234567"),
        ("",                  ""),
        (None,                ""),
    ]
    all_ok = True
    bad = []
    for raw, expected in cases:
        got = normalize_mobile(raw)
        if got != expected:
            all_ok = False
            bad.append(f"{raw!r}->{got!r} (want {expected!r})")
    _record("5a normalize_mobile unit cases", all_ok, "; ".join(bad))

    # Insert path: raw -> canonical on save
    _ensure_customer_group()
    _ensure_territory()
    # Clean up prior dup
    for n in (TEST_CUSTOMER_DUP,):
        if frappe.db.exists("Customer", n):
            frappe.delete_doc("Customer", n, force=1, ignore_permissions=True)

    cust = _ensure_customer(TEST_CUSTOMER, TEST_RAW_PHONE)
    stored = frappe.db.get_value("Customer", cust.name, "mobile_no")
    _record(
        "5b mobile stored in canonical form",
        stored == TEST_CANONICAL_PHONE,
        f"stored={stored!r}",
    )

    # Duplicate guard
    try:
        frappe.get_doc({
            "doctype": "Customer",
            "customer_name": TEST_CUSTOMER_DUP,
            "customer_group": TEST_GROUP,
            "territory": TEST_TERRITORY,
            "customer_type": "Individual",
            "mobile_no": "+234-803-123-4567",   # same canonical form
        }).insert(ignore_permissions=True)
        _record("5c duplicate mobile blocked", False, "second insert was allowed!")
    except frappe.exceptions.ValidationError as e:
        _record("5c duplicate mobile blocked", True, str(e)[:80])
    except Exception as e:
        _record("5c duplicate mobile blocked", False, f"wrong exception type: {type(e).__name__}: {e}")


# ---------------------------------------------------------------------------
# Feature 6 — Phone/name search API
# ---------------------------------------------------------------------------
def test_feature_6_search():
    print("\n[6] Customer phone/name search API")
    from posawesome.posawesome.api.customer_search import search_customers_by_phone_or_name

    _ensure_customer(TEST_CUSTOMER, TEST_RAW_PHONE)

    # 6a: exact canonical phone
    rows = search_customers_by_phone_or_name(query=TEST_CANONICAL_PHONE)
    _record(
        "6a search by canonical phone returns customer",
        any(r["name"] == TEST_CUSTOMER for r in rows),
        f"hits={[r['name'] for r in rows[:3]]}",
    )

    # 6b: raw 080... phone -> normalized -> finds it
    rows = search_customers_by_phone_or_name(query=TEST_RAW_PHONE)
    _record(
        "6b search by 080... raw phone returns customer",
        any(r["name"] == TEST_CUSTOMER for r in rows),
        f"hits={[r['name'] for r in rows[:3]]}",
    )

    # 6c: by name substring
    rows = search_customers_by_phone_or_name(query=TEST_PREFIX)
    _record(
        "6c search by name substring returns customer",
        any(r["name"] == TEST_CUSTOMER for r in rows),
        f"hits={[r['name'] for r in rows[:3]]}",
    )

    # 6d: empty query returns []
    rows = search_customers_by_phone_or_name(query="")
    _record("6d empty query returns []", rows == [], f"got len={len(rows)}")

    # 6e: returns required fields
    rows = search_customers_by_phone_or_name(query=TEST_CUSTOMER)
    needed = {"name", "customer_name", "mobile_no", "customer_group", "territory"}
    have = set(rows[0].keys()) if rows else set()
    _record(
        "6e response includes required fields",
        needed.issubset(have),
        f"missing={needed - have}",
    )


# ---------------------------------------------------------------------------
# Teardown — remove all SMK-* test data
# ---------------------------------------------------------------------------
def teardown():
    print("\n[*] Teardown")
    # Sales Invoices (only drafts created above; safe delete)
    for si in frappe.get_all(
        "Sales Invoice",
        filters={"customer": TEST_CUSTOMER, "docstatus": 0},
        pluck="name",
    ):
        try:
            frappe.delete_doc("Sales Invoice", si, force=1, ignore_permissions=True)
        except Exception:
            pass

    # PCRs
    for n in frappe.get_all(
        "LPG Price Change Request",
        filters={"reason": ["like", "SMK smoke test%"]},
        pluck="name",
    ):
        try:
            doc = frappe.get_doc("LPG Price Change Request", n)
            if doc.docstatus == 1:
                doc.cancel()
            frappe.delete_doc("LPG Price Change Request", n, force=1, ignore_permissions=True)
        except Exception:
            pass

    # Tiers created by tests OR by approved PCR
    for n in frappe.get_all(
        "LPG Outlet Price Tier",
        filters={"item_code": TEST_ITEM},
        pluck="name",
    ):
        try:
            frappe.delete_doc("LPG Outlet Price Tier", n, force=1, ignore_permissions=True)
        except Exception:
            pass

    # Customers
    for n in (TEST_CUSTOMER, TEST_CUSTOMER_DUP):
        if frappe.db.exists("Customer", n):
            try:
                frappe.delete_doc("Customer", n, force=1, ignore_permissions=True)
            except Exception:
                pass

    # Item / Group / Territory: leave in place if other docs reference them;
    # otherwise delete to keep DB clean.
    for dt, n in (
        ("Item", TEST_ITEM),
        ("Customer Group", TEST_GROUP),
        ("Territory", TEST_TERRITORY),
    ):
        if frappe.db.exists(dt, n):
            try:
                frappe.delete_doc(dt, n, force=1, ignore_permissions=True)
            except Exception as e:
                print(f"  skip delete {dt} {n}: {e}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("=" * 72)
    print(" POS Awesome — Phase-5 backend smoke test")
    print("=" * 72)
    try:
        test_feature_1_tiered_pricing()
    except Exception as e:
        _record("1 Tiered pricing (suite)", False, f"exception: {e}")
        traceback.print_exc()

    try:
        test_feature_4_workflow()
    except Exception as e:
        _record("4 Workflow (suite)", False, f"exception: {e}")
        traceback.print_exc()

    try:
        test_feature_5_mobile()
    except Exception as e:
        _record("5 Mobile (suite)", False, f"exception: {e}")
        traceback.print_exc()

    try:
        test_feature_6_search()
    except Exception as e:
        _record("6 Search (suite)", False, f"exception: {e}")
        traceback.print_exc()

    teardown()
    frappe.db.commit()

    print("\n" + "=" * 72)
    print(" SUMMARY")
    print("=" * 72)
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    failed = len(RESULTS) - passed
    for name, ok, detail in RESULTS:
        flag = "PASS" if ok else "FAIL"
        print(f"  [{flag}] {name}" + (f"  --  {detail}" if detail and not ok else ""))
    print(f"\n  Total: {len(RESULTS)}   Passed: {passed}   Failed: {failed}")
    print("=" * 72)
    if failed:
        sys.exit(1)


main()
