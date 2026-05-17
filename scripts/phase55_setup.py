"""
Phase-5.5 / pre-clone setup:

  1. Rename every '<num> - Sales and Marketing - SCL' Cost Center to embed
     its outlet (read from parent_cost_center).
  2. Fix '1117 - - Cash Sales - Asaba - SCL' double-dash typo.
  3. Create Cash Sales + Incoming Transfer + POS Incoming accounts for
     Oworo and Mafoluku (and any other outlet missing one of these three).
  4. Create 21 Branch entries (HRMS doctype) named after each outlet.
  5. Enable Accounting Dimensions for: Branch, Customer Group, plus a new
     custom 'Region' doctype with the 6 regions.
  6. Print a final mapping table the agent can use to seed clone_pos_profiles.

Idempotent. Re-run as many times as needed.

Run on bench:
    curl -fsSL https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/develop/scripts/phase55_setup.py \
      -o /tmp/phase55_setup.py && \
    bench --site sungasmis.v.frappe.cloud execute \
      "exec(open('/tmp/phase55_setup.py').read())"
"""

from __future__ import annotations

import re
import frappe

COMPANY = "SUNGAS COMPANY LIMITED"
ABBR = "SCL"

OUTLETS = [
    "Maba", "Sefu", "Ebutte", "Aseese",
    "Itele", "Iju-Otta", "Osi-Otta", "Ijoko",
    "Ikeja", "Oworo", "Pedro", "Bolade", "Mafoluku",
    "Eleme", "Reclamation",
    "Ekehuan", "Upper Mission", "Idowina", "Idokpa", "Okhuoromi",
    "Asaba",
]

OUTLET_REGION = {
    "Maba": "Ogun 1", "Sefu": "Ogun 1", "Ebutte": "Ogun 1", "Aseese": "Ogun 1",
    "Itele": "Ogun 2", "Iju-Otta": "Ogun 2", "Osi-Otta": "Ogun 2", "Ijoko": "Ogun 2",
    "Ikeja": "Lagos 1", "Oworo": "Lagos 1", "Pedro": "Lagos 1",
    "Bolade": "Lagos 1", "Mafoluku": "Lagos 1",
    "Eleme": "Rivers 1", "Reclamation": "Rivers 1",
    "Ekehuan": "Edo 1", "Upper Mission": "Edo 1", "Idowina": "Edo 1",
    "Idokpa": "Edo 1", "Okhuoromi": "Edo 1",
    "Asaba": "Delta 1",
}

# Account naming aliases: outlet -> [tokens to match account_name on].
OUTLET_ACCT_ALIASES = {
    "Ebutte": ["Ebutte", "Ebute"],
    "Iju-Otta": ["Iju-Otta", "Iju-Ota", "Iju Ota"],
    "Osi-Otta": ["Osi-Otta", "Osi-Ota", "Osi Ota"],
}


def _hr(t):
    print("\n" + "=" * 76 + "\n  " + t + "\n" + "-" * 76)


def _alias_tokens(outlet):
    return OUTLET_ACCT_ALIASES.get(outlet, [outlet])


def _find_account(outlet, search):
    """Return Account.name for the outlet matching `account_name LIKE '%search%'`."""
    for token in _alias_tokens(outlet):
        rows = frappe.get_all(
            "Account",
            filters={
                "company": COMPANY,
                "is_group": 0,
                "disabled": 0,
                "account_name": ["like", f"%{search}%"],
            },
            fields=["name", "account_name"],
        )
        for r in rows:
            n = r["account_name"].lower().replace("-", " ").replace("  ", " ")
            if token.lower().replace("-", " ") in n:
                return r["name"]
    return None


# -------------------------------------------------------------------- 1. Cost Center rename
def rename_cost_centers():
    _hr("1. Rename Cost Centers: embed outlet (from parent)")

    rows = frappe.get_all(
        "Cost Center",
        filters={"company": COMPANY, "is_group": 0,
                 "cost_center_name": "Sales and Marketing"},
        fields=["name", "cost_center_number", "parent_cost_center", "cost_center_name"],
    )
    print(f"  Found {len(rows)} plain 'Sales and Marketing' cost centers.")

    parent_outlet = {}
    parents = list({r["parent_cost_center"] for r in rows if r["parent_cost_center"]})
    for p in parents:
        pname = frappe.db.get_value("Cost Center", p, "cost_center_name") or ""
        # Pattern: "<lo> - <hi> - <Outlet>" or "<Outlet>".
        # Drop leading 'NNNN - NNNN -' prefix.
        cleaned = re.sub(r"^\s*\d+\s*-\s*\d+\s*-\s*", "", pname).strip()
        parent_outlet[p] = cleaned

    renamed = 0
    skipped = 0
    for r in rows:
        outlet = parent_outlet.get(r["parent_cost_center"])
        if not outlet:
            print(f"  [skip ] {r['name']:<45} (parent outlet unknown)")
            skipped += 1
            continue
        new_label = f"Sales and Marketing {outlet}"
        if new_label == r["cost_center_name"]:
            skipped += 1
            continue
        new_name = f"{r['cost_center_number']} - {new_label} - {ABBR}"
        if frappe.db.exists("Cost Center", new_name):
            skipped += 1
            continue
        frappe.rename_doc("Cost Center", r["name"], new_name, merge=False, force=True)
        cc = frappe.get_doc("Cost Center", new_name)
        cc.cost_center_name = new_label
        cc.save(ignore_permissions=True)
        renamed += 1
        print(f"  [renamed] {r['name']!r}  ->  {new_name!r}")
    frappe.db.commit()
    print(f"  Summary: renamed={renamed}, skipped={skipped}")


# -------------------------------------------------------------------- 2. Asaba typo
def fix_asaba_typo():
    _hr("2. Fix '1117 - - Cash Sales - Asaba - SCL' double-dash typo")
    bad = "1117 - - Cash Sales - Asaba - SCL"
    if not frappe.db.exists("Account", bad):
        print("  No action; bad name not present.")
        return
    good = "1117 - Cash Sales - Asaba - SCL"
    if frappe.db.exists("Account", good):
        print(f"  Both names exist; manual reconciliation required for {bad!r}.")
        return
    frappe.rename_doc("Account", bad, good, merge=False, force=True)
    a = frappe.get_doc("Account", good)
    a.account_name = "Cash Sales - Asaba"
    a.save(ignore_permissions=True)
    frappe.db.commit()
    print(f"  Renamed -> {good!r}")


# -------------------------------------------------------------------- 2b. POS Incoming typos
POS_INCOMING_RENAMES = [
    ("1540 - 1501 - POS Incoming - Itele - SCL",
     "1540 - POS Incoming - Itele - SCL",
     "POS Incoming - Itele", "1540"),
    ("1524 - POS Incoming - Idowina - idowina - SCL",
     "1524 - POS Incoming - Idowina - SCL",
     "POS Incoming - Idowina", "1524"),
    ("1531 - POS Incoming - Idowina - idokpa - SCL",
     "1531 - POS Incoming - Idokpa - SCL",
     "POS Incoming - Idokpa", "1531"),
    ("1535 - - POS Incoming - Asaba - SCL",
     "1535 - POS Incoming - Asaba - SCL",
     "POS Incoming - Asaba", "1535"),
]


def fix_pos_incoming_typos():
    _hr("2b. Fix POS Incoming account-name typos")
    fixed = 0
    for bad, good, account_name, number in POS_INCOMING_RENAMES:
        if not frappe.db.exists("Account", bad):
            print(f"  [skip] not present: {bad!r}")
            continue
        if frappe.db.exists("Account", good):
            # Same number can't exist twice; merge in manually.
            print(f"  [SKIP] both names exist - reconcile manually: {bad!r}")
            continue
        try:
            frappe.rename_doc("Account", bad, good, merge=False, force=True)
            a = frappe.get_doc("Account", good)
            a.account_name = account_name
            a.account_number = number
            a.save(ignore_permissions=True)
            fixed += 1
            print(f"  [OK ] {bad!r}\n         -> {good!r}")
        except Exception as exc:  # noqa: BLE001
            print(f"  [ERR] {bad!r}: {exc}")
    if fixed:
        frappe.db.commit()
    print(f"  Summary: {fixed} renamed.")


# -------------------------------------------------------------------- 3. Missing accounts
def _next_account_number(parent_account, prefix_digits):
    rows = frappe.get_all(
        "Account",
        filters={"parent_account": parent_account, "is_group": 0},
        fields=["account_number"],
    )
    # Also collect ALL account numbers across the whole company so we never
    # collide with a number used elsewhere (e.g. another parent group).
    company_rows = frappe.get_all(
        "Account",
        filters={"company": COMPANY, "is_group": 0},
        fields=["account_number"],
    )
    used = set()
    for r in rows + company_rows:
        n = r.get("account_number")
        if n and str(n).isdigit():
            used.add(int(n))
    # Start from the lowest valid candidate for this prefix range
    # (e.g. prefix '11' -> 1101) and scan up.
    start = int(f"{prefix_digits}01")
    candidate = start
    while candidate in used:
        candidate += 1
    return candidate


def _create_account(account_name, parent_account, account_type, account_number=None):
    full_name = f"{account_number} - {account_name} - {ABBR}" if account_number \
        else f"{account_name} - {ABBR}"
    if frappe.db.exists("Account", full_name):
        return full_name, "EXISTS"
    doc = frappe.get_doc({
        "doctype": "Account",
        "account_name": account_name,
        "account_number": str(account_number) if account_number else None,
        "parent_account": parent_account,
        "company": COMPANY,
        "account_type": account_type,
        "is_group": 0,
        "root_type": "Asset",
        "report_type": "Balance Sheet",
        "currency": "NGN",
    })
    doc.insert(ignore_permissions=True)
    return doc.name, "CREATED"


def create_missing_accounts():
    _hr("3. Create missing Cash/Transfer/POS-Incoming accounts")

    cash_parent = frappe.db.get_value(
        "Account",
        {"company": COMPANY, "is_group": 1,
         "account_name": ["like", "%Cash on Hand%"]},
        "name",
    ) or frappe.db.get_value(
        "Account",
        {"company": COMPANY, "is_group": 1,
         "name": ["like", "%1100%"]},
        "name",
    )
    transfer_parent = frappe.db.get_value(
        "Account",
        {"company": COMPANY, "is_group": 1,
         "name": ["like", "%Incoming Transfer/POS%"]},
        "name",
    ) or frappe.db.get_value(
        "Account",
        {"company": COMPANY, "is_group": 1,
         "name": ["like", "%1500 - 1549%"]},
        "name",
    )
    pos_parent = transfer_parent  # same group per screenshot

    print(f"  cash_parent     = {cash_parent}")
    print(f"  transfer_parent = {transfer_parent}")
    print(f"  pos_parent      = {pos_parent}")

    created = []
    for outlet in OUTLETS:
        cash = _find_account(outlet, "Cash Sales")
        transfer = _find_account(outlet, "Incoming Transfer")
        pos = _find_account(outlet, "POS Incoming")

        if not cash and cash_parent:
            num = _next_account_number(cash_parent, "11")
            n, st = _create_account(f"Cash Sales - {outlet}", cash_parent, "Cash", num)
            created.append((outlet, "Cash Sales", n, st))
            print(f"  [{st:<7}] {outlet:<16} Cash Sales -> {n}")

        if not transfer and transfer_parent:
            num = _next_account_number(transfer_parent, "15")
            n, st = _create_account(f"Incoming Transfer - {outlet}", transfer_parent, "Bank", num)
            created.append((outlet, "Incoming Transfer", n, st))
            print(f"  [{st:<7}] {outlet:<16} Incoming Transfer -> {n}")

        if not pos and pos_parent:
            num = _next_account_number(pos_parent, "15")
            n, st = _create_account(f"POS Incoming - {outlet}", pos_parent, "Bank", num)
            created.append((outlet, "POS Incoming", n, st))
            print(f"  [{st:<7}] {outlet:<16} POS Incoming -> {n}")

    if not created:
        print("  (nothing to create; everything exists)")
    frappe.db.commit()


# -------------------------------------------------------------------- 4. Branches
def create_branches():
    _hr("4. Create HRMS Branch entries (one per outlet)")
    if not frappe.db.exists("DocType", "Branch"):
        print("  Branch doctype not installed; skipping.")
        return
    for outlet in OUTLETS:
        if frappe.db.exists("Branch", outlet):
            print(f"  [exists] {outlet}")
            continue
        frappe.get_doc({"doctype": "Branch", "branch": outlet}).insert(ignore_permissions=True)
        print(f"  [CREATED] {outlet}")
    frappe.db.commit()


# -------------------------------------------------------------------- 5. Region doctype + entries + Accounting Dimensions
def setup_region_doctype():
    _hr("5a. Region doctype + 6 region entries")
    dt = "Sungas Region"
    if not frappe.db.exists("DocType", dt):
        doc = frappe.get_doc({
            "doctype": "DocType",
            "name": dt,
            "module": "POSAwesome",
            "custom": 1,
            "naming_rule": "By fieldname",
            "autoname": "field:region_name",
            "fields": [
                {"fieldname": "region_name", "label": "Region",
                 "fieldtype": "Data", "reqd": 1, "unique": 1, "in_list_view": 1},
            ],
            "permissions": [
                {"role": "System Manager", "read": 1, "write": 1,
                 "create": 1, "delete": 1},
                {"role": "Accounts Manager", "read": 1, "write": 1, "create": 1},
                {"role": "Sales Manager", "read": 1},
            ],
        })
        doc.insert(ignore_permissions=True)
        print(f"  [CREATED doctype] {dt}")
    else:
        print(f"  [exists doctype] {dt}")

    for region in sorted(set(OUTLET_REGION.values())):
        if frappe.db.exists(dt, region):
            continue
        frappe.get_doc({"doctype": dt, "region_name": region}).insert(ignore_permissions=True)
        print(f"  [CREATED region] {region}")
    frappe.db.commit()


def setup_accounting_dimensions():
    _hr("5b. Enable Accounting Dimensions: Branch + Customer Group + Sungas Region")
    targets = [
        ("Branch", "Branch", "branch"),
        ("Customer Group", "Customer Group", "customer_group"),
        ("Sungas Region", "Sungas Region", "sungas_region"),
    ]
    for label, doctype, fieldname in targets:
        if not frappe.db.exists("DocType", doctype):
            print(f"  [skip] {doctype} doctype not present")
            continue
        if frappe.db.exists("Accounting Dimension", doctype):
            print(f"  [exists] Accounting Dimension '{doctype}'")
            continue
        try:
            doc = frappe.get_doc({
                "doctype": "Accounting Dimension",
                "document_type": doctype,
                "label": label,
                "fieldname": fieldname,
                "disabled": 0,
            })
            doc.insert(ignore_permissions=True)
            print(f"  [CREATED] Accounting Dimension '{doctype}'")
        except Exception as exc:
            print(f"  [ERROR] {doctype}: {exc}")
    frappe.db.commit()


# -------------------------------------------------------------------- 6. Print final map
def print_outlet_map():
    _hr("6. Final outlet -> accounts/cost-center map (use for clone)")
    rows = []
    for outlet in OUTLETS:
        cash = _find_account(outlet, "Cash Sales")
        transfer = _find_account(outlet, "Incoming Transfer")
        pos = _find_account(outlet, "POS Incoming")
        cc = frappe.get_all(
            "Cost Center",
            filters={"company": COMPANY, "is_group": 0,
                     "cost_center_name": ["like", f"%Sales and Marketing {outlet}%"]},
            pluck="name",
            limit=1,
        )
        cc_name = cc[0] if cc else None
        rows.append({"outlet": outlet, "cash": cash, "transfer": transfer,
                     "pos": pos, "cost_center": cc_name,
                     "region": OUTLET_REGION.get(outlet)})
        ok = "OK " if all([cash, transfer, pos, cc_name]) else "MISS"
        print(f"  [{ok}] {outlet:<16} cash={cash!r}")
        print(f"             transfer={transfer!r}")
        print(f"             pos={pos!r}")
        print(f"             cost_center={cc_name!r}  region={OUTLET_REGION.get(outlet)!r}")
    return rows


def main():
    print("=" * 76)
    print(f"  Phase-5.5 setup -- {COMPANY}")
    print("=" * 76)
    rename_cost_centers()
    fix_asaba_typo()
    fix_pos_incoming_typos()
    create_missing_accounts()
    create_branches()
    setup_region_doctype()
    setup_accounting_dimensions()
    print_outlet_map()
    print("\nDone.")


try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
