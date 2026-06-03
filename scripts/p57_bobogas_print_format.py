"""p57_bobogas_print_format.py
==============================
Clone the active Sungas-branded receipt Print Format into a BOBO GAS variant
and assign it to the Itele outlet's POS Profile.

Why: Itele outlet trades under the "Bobo Gas" sub-brand. Customers expect that
business name on their receipts, not "Sungas Company Limited". Rather than
swap the corporate name at the company level (which would break every other
outlet), we ship a per-outlet print format.

Run:
  bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/p57_bobogas.py').read())"

Configurable in the top section: change SOURCE_FORMAT, TARGET_FORMAT,
ITELE_PROFILE, REPLACEMENTS to match your data before executing.

Idempotency: if TARGET_FORMAT already exists, the script overwrites its HTML
with a freshly rebuilt copy (so re-running picks up upstream changes).
The POS Profile binding is also idempotent (no-op if already set).
"""
import frappe  # type: ignore # noqa: F401
import re

# === EDIT THESE TO MATCH YOUR DATA ===========================================
# Run this first to list candidate sources:
#   bench --site sungasmis.v.frappe.cloud list-format-fields "Print Format" name
# Or open: https://sungasmis.v.frappe.cloud/app/print-format
SOURCE_FORMAT = "POS Invoice"                # the existing Sungas-branded receipt
TARGET_FORMAT = "POS Invoice - BOBO GAS"     # the new clone for Itele
ITELE_PROFILE = "POS - SCL - Itele"          # the POS Profile to bind to

# Strings to replace in the HTML/header/footer. Case-insensitive whole-string
# replace -- we use re.IGNORECASE with word-boundary anchors to avoid touching
# fragments like "sungas-internal" in CSS class names.
REPLACEMENTS = [
    (r"\bSungas\s+Company\s+Limited\b", "Bobo Gas"),
    (r"\bSungas\s+Company\b",            "Bobo Gas"),
    (r"\bSCL\s+Sungas\b",                "Bobo Gas"),
    (r"\bSungas\b",                      "Bobo Gas"),
    (r"\bSCL\b",                         "BG"),
]
# =============================================================================


def _rebrand(text: str | None) -> str | None:
    if not text:
        return text
    out = text
    for pattern, replacement in REPLACEMENTS:
        out = re.sub(pattern, replacement, out, flags=re.IGNORECASE)
    return out


def clone_print_format():
    if not frappe.db.exists("Print Format", SOURCE_FORMAT):
        print(f"  ! Source print format '{SOURCE_FORMAT}' not found.")
        print("    Available formats:")
        names = frappe.get_all("Print Format", fields=["name", "doc_type"], order_by="name")
        for n in names:
            print(f"      - {n.name}  (doctype: {n.doc_type})")
        return False

    src = frappe.get_doc("Print Format", SOURCE_FORMAT)
    is_new = not frappe.db.exists("Print Format", TARGET_FORMAT)

    if is_new:
        target = frappe.copy_doc(src)
        target.name = TARGET_FORMAT
        target.print_format_type = src.print_format_type
        target.standard = "No"
        target.disabled = 0
        target.module = src.module
    else:
        target = frappe.get_doc("Print Format", TARGET_FORMAT)

    # Apply rebranded fields
    target.html = _rebrand(src.html)
    target.css = src.css  # CSS is class names, do NOT rebrand
    target.print_designer_header = _rebrand(getattr(src, "print_designer_header", None))
    target.print_designer_body = _rebrand(getattr(src, "print_designer_body", None))
    target.print_designer_after_table = _rebrand(getattr(src, "print_designer_after_table", None))
    target.print_designer_footer = _rebrand(getattr(src, "print_designer_footer", None))

    # Force-copy structural fields from source so the clone tracks layout updates
    for f in ("doc_type", "print_format_type", "font_size", "margin_top",
              "margin_bottom", "margin_left", "margin_right", "page_number",
              "align_labels_right", "show_section_headings", "line_breaks",
              "absolute_value", "default_print_language"):
        if hasattr(src, f):
            setattr(target, f, getattr(src, f))

    if is_new:
        target.insert(ignore_permissions=True)
        print(f"  + Created Print Format: {TARGET_FORMAT}")
    else:
        target.save(ignore_permissions=True)
        print(f"  ~ Updated Print Format: {TARGET_FORMAT}")
    return True


def bind_to_itele():
    if not frappe.db.exists("POS Profile", ITELE_PROFILE):
        print(f"  ! POS Profile '{ITELE_PROFILE}' not found. Available profiles:")
        for p in frappe.get_all("POS Profile", fields=["name", "disabled"], order_by="name"):
            print(f"      - {p.name}  (disabled={p.disabled})")
        return False

    profile = frappe.get_doc("POS Profile", ITELE_PROFILE)
    current = (profile.print_format or "").strip()
    if current == TARGET_FORMAT:
        print(f"  = POS Profile '{ITELE_PROFILE}' already prints '{TARGET_FORMAT}', no change.")
        return True

    profile.print_format = TARGET_FORMAT
    profile.save(ignore_permissions=True)
    print(f"  + POS Profile '{ITELE_PROFILE}' print_format: '{current}' -> '{TARGET_FORMAT}'")
    return True


def main():
    print("\n=== Bobo Gas print format setup for Itele ===")
    ok1 = clone_print_format()
    if not ok1:
        print("\nAborting -- could not clone print format. Edit SOURCE_FORMAT above.")
        return
    ok2 = bind_to_itele()
    if not ok2:
        print("\nClone saved but POS Profile binding failed. Edit ITELE_PROFILE above.")
        return
    frappe.db.commit()
    print("\n+ Done. Test by reprinting an Itele invoice -- should now show 'Bobo Gas'.")
    print()


main()
