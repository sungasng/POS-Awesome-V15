"""
p57: Definitive POS Awesome flow simulation -- as Peace.

Replicates the exact server-side flow POS Awesome runs when the cart loads:
  1. Read POS Profile (POS - Ikeja) -- as Peace.
  2. Read the default Customer (and its Territory).
  3. Read a sample Item from the active Item Group of the profile.
  4. Try to instantiate a Sales Invoice with that customer + that item + POS profile.
  5. Try to save it as draft (which is what POS Awesome does on each cart event).

Prints exact tracebacks for whichever step fails first.

Read-only. Rolls back any changes.

Run:
    SHA=<commit>
    cd ~/frappe-bench
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/$SHA/scripts/p57_peace_flow_sim.py" -o /tmp/p57f.py
    bench --site sungasmis.v.frappe.cloud execute "(exec(open('/tmp/p57f.py').read(), globals()) or (lambda **k: None))"
"""
from __future__ import annotations
from pathlib import Path
import traceback
import frappe

PEACE = "peace.effiong@sungas.org"
POS_PROFILE = "POS - Ikeja"


def main():
    L = []
    p = L.append
    p("# Peace -- POS Awesome flow simulation")
    p("")

    pp_admin = frappe.get_doc("POS Profile", POS_PROFILE)
    default_customer = (
        pp_admin.customer
        or frappe.db.get_value("Selling Settings", None, "customer_group")
        or "Walk-in Customer"
    )
    p(f"- POS Profile `{POS_PROFILE}` (as Admin):")
    p(f"  - default customer (pp.customer): `{pp_admin.customer}`")
    p(f"  - applicable_for_users: {[u.user for u in pp_admin.applicable_for_users]}")
    p("")

    if pp_admin.customer:
        cust_terr = frappe.db.get_value("Customer", pp_admin.customer, "territory")
        cust_group = frappe.db.get_value("Customer", pp_admin.customer, "customer_group")
        p(f"- Default Customer `{pp_admin.customer}`: territory=`{cust_terr}`, customer_group=`{cust_group}`")
        if cust_terr and cust_terr != "Ikeja":
            p(f"- :rotating_light: **LIKELY ROOT CAUSE**: default customer's territory is `{cust_terr}`,")
            p(f"  but Peace's User Permission restricts her to Territory=`Ikeja`.")
            p(f"  POS Awesome cannot load this customer for her, hence 'Not permitted'.")
    p("")

    # Switch to Peace
    frappe.set_user(PEACE)
    p("## As Peace -- replicating cart flow")

    # 1. Read POS Profile
    p("### 1. Read POS Profile")
    try:
        pp = frappe.get_doc("POS Profile", POS_PROFILE)
        p(f"- :white_check_mark: read POS Profile (default customer = `{pp.customer}`)")
    except frappe.PermissionError as e:
        p(f"- :x: PermissionError reading POS Profile: {e}")
        p(""); _save(L); return
    except Exception as e:
        p(f"- :warning: {type(e).__name__}: {e}")
        p(""); _save(L); return

    # 2. Read default customer
    p("### 2. Read default customer")
    if not pp.customer:
        p("- (no default customer on profile -- skipping)")
    else:
        try:
            c = frappe.get_doc("Customer", pp.customer)
            p(f"- :white_check_mark: read Customer `{c.name}` (territory=`{c.territory}`, group=`{c.customer_group}`)")
        except frappe.PermissionError as e:
            p(f"- :x: **PermissionError reading default Customer: {e}**")
            p(f"- This is almost certainly what POS Awesome reports as 'Not permitted on Sales Invoice'")
        except Exception as e:
            p(f"- :warning: {type(e).__name__}: {e}")
    p("")

    # 3. Try to find a sample item
    p("### 3. Read a sample Item that the cashier sees")
    try:
        items = frappe.get_list(
            "Item",
            filters={"disabled": 0, "is_sales_item": 1},
            fields=["name", "item_name"],
            limit=3,
            ignore_permissions=False,
        )
        if not items:
            p("- :x: Peace sees ZERO sales items. User Permission likely blocks Item read.")
        else:
            p(f"- :white_check_mark: Peace can see {len(items)} sample items: {[i['name'] for i in items]}")
        sample_item = items[0]["name"] if items else None
    except Exception as e:
        p(f"- :warning: {type(e).__name__}: {e}")
        sample_item = None
    p("")

    # 4. Instantiate full Sales Invoice as Peace, with default cust + sample item
    p("### 4. Instantiate Sales Invoice as Peace (with cust + item)")
    if not pp.customer:
        p("- (no default customer, skipping)")
    elif not sample_item:
        p("- (no readable item, skipping)")
    else:
        try:
            si = frappe.new_doc("Sales Invoice")
            si.is_pos = 1
            si.pos_profile = POS_PROFILE
            si.customer = pp.customer
            si.company = pp.company
            si.update_stock = 1
            si.append("items", {
                "item_code": sample_item,
                "qty": 1,
            })
            p(f"- :white_check_mark: in-memory document built")
            # 5. Try to save as draft (this is what POS Awesome does)
            try:
                si.set_missing_values()
                p("- :white_check_mark: set_missing_values succeeded")
                # do NOT save -- just stop here; the test is enough
            except frappe.PermissionError as e:
                p(f"- :x: PermissionError at set_missing_values: {e}")
            except Exception as e:
                p(f"- :warning: {type(e).__name__} at set_missing_values: {e}")
                p("```")
                p(traceback.format_exc())
                p("```")
        except frappe.PermissionError as e:
            p(f"- :x: PermissionError during build: {e}")
            p("```")
            p(traceback.format_exc())
            p("```")
        except Exception as e:
            p(f"- :warning: {type(e).__name__}: {e}")
            p("```")
            p(traceback.format_exc())
            p("```")
    p("")

    frappe.set_user("Administrator")
    _save(L)


def _save(L):
    out = "\n".join(L)
    Path("/tmp/p57_peace_flow.log").write_text(out, encoding="utf-8")
    print(out)
    print()
    print(f"  Log: /tmp/p57_peace_flow.log")


main()
