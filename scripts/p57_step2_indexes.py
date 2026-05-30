"""
Phase 5.7 / Step 2: Add composite indexes on hot POS tables.

Adds:
  - tabSales Invoice (pos_profile, posting_date, docstatus)  -- POS list view
  - tabSales Invoice (customer, posting_date)                -- customer history page
  - tabSales Invoice Item (item_code, parent)                -- item velocity reports
  - tabStock Ledger Entry (warehouse, posting_date, posting_time, name) -- stock report
  - tabPayment Entry (party, posting_date)                   -- customer ledger

Idempotent: skips if index already present (SHOW INDEX check).

Run:
    SHA=<commit>
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/$SHA/scripts/p57_step2_indexes.py" -o /tmp/p57b.py
    bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/p57b.py').read())"

WARNING: Each ALTER TABLE on a large table can take 5-30s. Run during low
traffic. Frappe Cloud will not let MariaDB block long enough to hurt.
"""

from __future__ import annotations
import frappe


INDEXES = [
    # (table, index_name, columns)
    ("tabSales Invoice",      "idx_pos_profile_date_status",  "pos_profile, posting_date, docstatus"),
    ("tabSales Invoice",      "idx_customer_date",            "customer, posting_date"),
    ("tabSales Invoice Item", "idx_item_parent",              "item_code, parent"),
    ("tabStock Ledger Entry", "idx_warehouse_date",           "warehouse, posting_date, posting_time, name"),
    ("tabPayment Entry",      "idx_party_date",               "party, posting_date"),
]


def index_exists(table: str, name: str) -> bool:
    rows = frappe.db.sql(f"SHOW INDEX FROM `{table}` WHERE Key_name = %s", (name,), as_dict=True)
    return bool(rows)


def main() -> None:
    print("=" * 72)
    print(" Phase 5.7 / Step 2 -- Composite indexes")
    print("=" * 72)
    print()
    added = skipped = errored = 0
    for tbl, name, cols in INDEXES:
        try:
            if index_exists(tbl, name):
                print(f"  = SKIP  `{tbl}`.{name} -- already exists")
                skipped += 1
                continue
            print(f"  ~ ADD   `{tbl}`.{name} ({cols}) ...")
            frappe.db.sql(f"CREATE INDEX `{name}` ON `{tbl}` ({cols})")
            frappe.db.commit()
            print(f"  + DONE  `{tbl}`.{name}")
            added += 1
        except Exception as e:
            print(f"  ! FAIL  `{tbl}`.{name}: {e!r}")
            errored += 1
    print()
    print(f"  added={added}  skipped={skipped}  errored={errored}")


try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
