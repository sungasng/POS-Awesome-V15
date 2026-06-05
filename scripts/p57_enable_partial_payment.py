"""p57_enable_partial_payment.py
=============================
Flip `posa_allow_partial_payment` ON for all enabled POS Profiles.

Context: 2026-06-03 UAT discovered split payments (e.g. NGN 140k cash + 200k POS
for a 340k invoice) were being rejected with:

    "Cash payment cannot be less than invoice total when partial payment is not
     allowed"

POS Awesome's `submit()` checks `pos_profile.posa_allow_partial_payment` and
hard-rejects mixed-tender sales if it's off. The flag was unchecked on all 22
outlet profiles after the May 2026 clone, so this just turns it on.

Run via:
    bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/p57_enable_partial_payment.py').read())"

After flipping, cashiers can take split-tender sales (e.g. cash + POS, cash +
transfer, all combinations) provided the total still equals invoice total.
"""
import frappe  # type: ignore # noqa: F401


def main():
    profiles = frappe.get_all(
        "POS Profile",
        filters={"disabled": 0},
        fields=["name", "posa_allow_partial_payment"],
        order_by="name",
    )
    flipped, already_on, total = [], [], len(profiles)
    for p in profiles:
        if p.posa_allow_partial_payment:
            already_on.append(p.name)
            continue
        frappe.db.set_value(
            "POS Profile",
            p.name,
            "posa_allow_partial_payment",
            1,
            update_modified=False,
        )
        flipped.append(p.name)

    frappe.db.commit()

    print(f"\nPOS Profile partial-payment audit ({total} enabled profiles)")
    print(f"  Already ON: {len(already_on)}")
    print(f"  Just flipped ON: {len(flipped)}")
    if flipped:
        for n in flipped:
            print(f"    + {n}")
    print()


# _BENCH_EXEC_FIX: bench execute "exec(...)" runs scripts with separate
# globals/locals dicts, so module-level functions can't see other module-level
# helpers. Copying locals -> globals before invoking main() fixes the scope.
globals().update(locals())
main()
