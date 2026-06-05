"""p57_dump_print_format.py
============================
Read-only dumper: write the HTML/CSS of an existing Print Format to a file
so I can review and modify it (preserving outlet address, phone, promo
text, and barcode that the user already configured by hand).

Output: writes to /tmp/printformat_dump.txt (so it survives the bench
container restarts and you can `cat` or `curl` it to read).

Run:
  bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/p57_dump.py').read())"

Then to read the output on the bench server:
  cat /tmp/printformat_dump.txt
"""
import frappe  # type: ignore # noqa: F401

# === EDIT ================================================================
PRINT_FORMAT = "Sungas Thermal 58mm"  # the format to dump
OUTPUT_PATH = "/tmp/printformat_dump.txt"
# =========================================================================


def main():
    if not frappe.db.exists("Print Format", PRINT_FORMAT):
        print(f"  ! Print Format '{PRINT_FORMAT}' not found.")
        names = frappe.get_all("Print Format", fields=["name", "doc_type", "module"], order_by="name")
        for n in names:
            print(f"      - {n.name}  (doctype: {n.doc_type}, module: {n.module})")
        return

    pf = frappe.get_doc("Print Format", PRINT_FORMAT)
    out = []
    out.append(f"=== Print Format: {pf.name} ===")
    out.append(f"doc_type:           {pf.doc_type}")
    out.append(f"print_format_type:  {pf.print_format_type}")
    out.append(f"standard:           {pf.standard}")
    out.append(f"disabled:           {pf.disabled}")
    out.append(f"module:             {pf.module}")
    out.append(f"font_size:          {pf.font_size}")
    out.append(f"margins:            top={pf.margin_top} bottom={pf.margin_bottom} left={pf.margin_left} right={pf.margin_right}")
    out.append("")
    out.append("=== HTML ===")
    out.append(pf.html or "(no html)")
    out.append("")
    out.append("=== CSS ===")
    out.append(pf.css or "(no css)")
    out.append("")
    out.append("=== Print Designer Header ===")
    out.append(getattr(pf, "print_designer_header", "") or "(none)")
    out.append("")
    out.append("=== Print Designer Body ===")
    out.append(getattr(pf, "print_designer_body", "") or "(none)")
    out.append("")
    out.append("=== Print Designer After Table ===")
    out.append(getattr(pf, "print_designer_after_table", "") or "(none)")
    out.append("")
    out.append("=== Print Designer Footer ===")
    out.append(getattr(pf, "print_designer_footer", "") or "(none)")
    out.append("")
    out.append("=== END ===")

    text = "\n".join(out)
    with open(OUTPUT_PATH, "w") as fh:
        fh.write(text)

    print(f"  + Dumped {len(text)} bytes to {OUTPUT_PATH}")
    print(f"\n--- Preview (first 4000 chars) ---\n")
    print(text[:4000])
    if len(text) > 4000:
        print(f"\n... ({len(text) - 4000} more bytes in {OUTPUT_PATH})")


# _BENCH_EXEC_FIX: bench execute "exec(...)" runs scripts with separate
# globals/locals dicts, so module-level functions can't see other module-level
# helpers. Copying locals -> globals before invoking main() fixes the scope.
globals().update(locals())
main()
