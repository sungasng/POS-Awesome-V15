"""
p57: Targeted Peace POS-Awesome Sales Invoice block diagnostic.

Tests, AS PEACE:
  1. has_permission with throw=True on Sales Invoice / Sales Invoice Item /
     POS Profile (POS-Ikeja) / Customer / Item.
  2. Confirms that Territory "Ikeja" referenced by her User Permission
     actually exists (case-sensitive!).
  3. Lists all Territory names so we can compare.
  4. Verifies POS Profile "POS - Ikeja" has a Customer Group and Territory
     that Peace can see.
  5. Tries to instantiate (NOT save) a draft Sales Invoice as Peace, with
     the POS Profile's defaults, to trigger the exact validation error she
     hits.

Read-only. No writes.

Run:
    SHA=<commit>
    cd ~/frappe-bench
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/$SHA/scripts/p57_peace_blocked.py" -o /tmp/p57b.py
    bench --site sungasmis.v.frappe.cloud execute "(exec(open('/tmp/p57b.py').read(), globals()) or (lambda **k: None))"
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
    p("# Peace Effiong -- POS Awesome 'Not permitted' targeted diagnostic")
    p("")

    user = frappe.get_doc("User", PEACE)
    p(f"- Roles: {sorted(r.role for r in user.roles)}")
    ups = frappe.db.sql("""
        select allow, for_value, applicable_for, apply_to_all_doctypes
        from `tabUser Permission` where user = %s
    """, (PEACE,), as_dict=True)
    p(f"- User Permissions: {ups}")
    p("")

    # 1. Does Territory record "Ikeja" actually exist?
    p("## 1. Territory record sanity")
    exact = frappe.db.exists("Territory", "Ikeja")
    p(f"- frappe.db.exists('Territory', 'Ikeja') = {exact}")
    if not exact:
        p("- :rotating_light: The User Permission references a Territory that DOES NOT EXIST.")
        p("- This will cause Frappe to silently filter Peace out of *every* doctype it links to Territory.")
    territories = [r["name"] for r in frappe.db.sql(
        "select name from `tabTerritory` order by name", as_dict=True)]
    p(f"- All Territories in system ({len(territories)}):")
    for t in territories:
        marker = "  <-- THIS IS PROBABLY THE INTENDED ONE" if "ikeja" in t.lower() and t != "Ikeja" else ""
        p(f"  - `{t}`{marker}")
    p("")

    # 2. POS Profile inspection
    p("## 2. POS Profile `POS - Ikeja` inspection")
    if not frappe.db.exists("POS Profile", POS_PROFILE):
        p(f"- :rotating_light: POS Profile `{POS_PROFILE}` does not exist")
    else:
        pp = frappe.get_doc("POS Profile", POS_PROFILE)
        p(f"- name: {pp.name}")
        p(f"- company: {pp.company}")
        p(f"- warehouse: {pp.warehouse}")
        p(f"- territory: {getattr(pp, 'territory', '(none)')}")
        p(f"- customer_group: {pp.customer_group}")
        p(f"- cost_center: {pp.cost_center}")
        p(f"- selling_price_list: {pp.selling_price_list}")
        p(f"- applicable_for_users: {[u.user for u in pp.applicable_for_users] if pp.applicable_for_users else '(open to all)'}")
        if PEACE not in [u.user for u in pp.applicable_for_users]:
            if pp.applicable_for_users:
                p(f"- :rotating_light: Peace is NOT in the `applicable_for_users` of this POS Profile.")
    p("")

    # 3. has_permission throw=True as Peace on each related doctype
    p("## 3. has_permission(throw=True) for Peace on POS-related doctypes")
    frappe.set_user(PEACE)
    targets = ["Sales Invoice", "POS Invoice", "POS Profile", "POS Opening Shift",
               "Customer", "Item", "Sales Invoice Item"]
    for dt in targets:
        try:
            frappe.has_permission(dt, ptype="create", throw=True)
            p(f"- `{dt}` -> create OK")
        except frappe.PermissionError as e:
            p(f"- `{dt}` -> :x: PermissionError: {e}")
        except Exception as e:
            p(f"- `{dt}` -> :warning: {type(e).__name__}: {e}")

    # 4. Try to instantiate a Sales Invoice as Peace (NOT saving)
    p("")
    p("## 4. Instantiate Sales Invoice as Peace (no save)")
    try:
        si = frappe.new_doc("Sales Invoice")
        si.is_pos = 1
        si.pos_profile = POS_PROFILE
        si.update_stock = 1
        # Don't add items / customer -- just see if the constructor + permission stage passes
        p("- :white_check_mark: new_doc + assign fields succeeded (no save).")
    except frappe.PermissionError as e:
        p(f"- :x: PermissionError at new_doc stage: {e}")
        p("```")
        p(traceback.format_exc())
        p("```")
    except Exception as e:
        p(f"- :warning: {type(e).__name__}: {e}")
        p("```")
        p(traceback.format_exc())
        p("```")
    finally:
        frappe.set_user("Administrator")
    p("")

    # 5. Verify the POS Awesome backend method 'submit_invoice' / 'get_items' is reachable
    p("## 5. Hint")
    p("If section 4 fails with PermissionError on a specific child doctype (e.g. Customer / Item / POS Profile), ")
    p("that's the missing piece. If section 1 shows the Territory record `Ikeja` does NOT exist but, say, ")
    p("`Lagos - Ikeja` or `Ikeja-SCL` does, then the User Permission row is pointing to a non-existent value -- ")
    p("delete the bad User Permission row OR change `for_value` to the correct Territory name.")
    p("")

    out = "\n".join(L)
    Path("/tmp/p57_peace_blocked.log").write_text(out, encoding="utf-8")
    print(out)
    print()
    print(f"  Log: /tmp/p57_peace_blocked.log")


main()
