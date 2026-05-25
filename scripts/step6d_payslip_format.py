"""
Phase 6 / Step 6d: Sungas-branded Salary Slip Print Format.

Creates (or updates) a Print Format named 'Sungas Payslip' for the
Salary Slip doctype, with a clean Nigerian-payroll layout:

  - Header with Sungas brand + payslip period
  - Employee block (name/ID/department/designation/branch/grade/bank)
  - Earnings table (only non-statistical, non-zero rows)
  - Deductions table (only non-statistical, non-zero rows)
  - Gross / Total Deduction / Net Pay
  - Net Pay in words
  - "Employer Contributions on Your Behalf" transparency block
    (statistical components: NSITF, Pension ER, Medical Allowance)
  - Bank disbursement details (last 4 digits masked)
  - Footer with computer-generation notice

Skipped from standard layout (visible in core print format but noise for Sungas):
  - All `*_company_currency` duplicates (NGN==NGN)
  - India-tax engine internals (Annual Taxable Amount, CTC, Future Income
    Tax, Standard Tax Exemption, etc.)

Upgrade-safe:
  - `is_standard = "No"` -- Frappe never touches it on bench update.
  - `custom_format = 1`  -- forces use of our Jinja, ignores doctype meta.
  - `module = "Custom"`  -- groups under user-created formats.

Run:
    SHA=<commit>
    curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/$SHA/scripts/step6d_payslip_format.py" -o /tmp/s6d.py
    bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/s6d.py').read())"

Make it the default for all slips:
    Desk -> Payroll Settings -> Salary Slip Print Format -> 'Sungas Payslip'
    (or run `bench set-default salary_slip_print_format 'Sungas Payslip'`)
"""

from __future__ import annotations
import frappe


FORMAT_NAME = "Sungas Payslip"


# --- Jinja template (HTML + minimal inline CSS for A4 printing) ---------------
PAYSLIP_HTML = r"""
{% set company_doc = frappe.get_cached_doc("Company", doc.company) %}
{% set emp = frappe.get_cached_doc("Employee", doc.employee) %}
{% set period_label = frappe.utils.formatdate(doc.start_date, "MMMM yyyy") %}

<style>
  .sungas-slip { font-family: "Helvetica", "Arial", sans-serif; color:#1f2937;
                 font-size:8.5pt; line-height:1.2; max-width:380px; margin:0 auto; }
  .sungas-slip h1 { font-size:11pt; margin:0; color:#0f3a52; letter-spacing:0.3px; }
  .sungas-slip h2 { font-size:8pt; margin:0 0 2px 0; color:#0f3a52;
                    text-transform:uppercase; letter-spacing:0.4px;
                    border-bottom:1px solid #0f3a52; padding-bottom:1px; }
  .sungas-slip .hdr { border-bottom:1.5px solid #0f3a52; padding-bottom:4px; margin-bottom:6px;
                      text-align:center; }
  .sungas-slip .hdr-sub { font-size:7.5pt; color:#64748b; margin-top:1px; }
  .sungas-slip .hdr-meta { font-size:7pt; color:#475569; margin-top:2px; }
  .sungas-slip .grid-2 { display:grid; grid-template-columns:1fr 1fr; gap:8px;
                         margin-bottom:6px; font-size:7.5pt; }
  .sungas-slip .grid-2 .row { display:grid; grid-template-columns:54px 1fr; padding:0; }
  .sungas-slip .grid-2 .lbl { color:#64748b; }
  .sungas-slip .grid-2 .val { font-weight:600; }
  .sungas-slip table.tbl { width:100%; border-collapse:collapse; margin:0;
                           font-size:8pt; }
  .sungas-slip table.tbl td { padding:1.5px 4px; vertical-align:top; }
  .sungas-slip table.tbl td.amt { text-align:right; font-variant-numeric:tabular-nums; }
  .sungas-slip table.tbl tr.tbl-row td { border-bottom:1px dashed #e2e8f0; }
  .sungas-slip table.tbl tr.tbl-total td { border-top:1px solid #0f3a52;
                                            padding-top:3px; font-weight:700; }
  .sungas-slip .ed-grid { display:grid; grid-template-columns:1fr 1fr; gap:10px;
                          margin-bottom:6px; }
  .sungas-slip .net-box { background:#f0f7fc; border:1px solid #0f3a52;
                          padding:5px 8px; margin:6px 0 3px 0;
                          display:flex; justify-content:space-between; align-items:center; }
  .sungas-slip .net-box .lbl { font-size:8pt; color:#0f3a52; font-weight:600;
                                text-transform:uppercase; letter-spacing:0.4px; }
  .sungas-slip .net-box .val { font-size:11pt; font-weight:700; color:#0f3a52;
                                font-variant-numeric:tabular-nums; }
  .sungas-slip .words { font-style:italic; color:#475569; margin:0 0 5px 0; font-size:7.5pt; }
  .sungas-slip .stat-block { background:#fafafa; border:1px solid #e2e8f0;
                              padding:3px 6px; margin-bottom:5px; font-size:7.5pt;
                              color:#475569; }
  .sungas-slip .stat-block h2 { font-size:7.5pt; border:none; padding:0; margin-bottom:2px; color:#64748b; }
  .sungas-slip .stat-block table { width:100%; }
  .sungas-slip .stat-block td { padding:1px 3px; }
  .sungas-slip .stat-block td.amt { text-align:right; font-variant-numeric:tabular-nums; }
  .sungas-slip .pay-details { font-size:7.5pt; display:grid; grid-template-columns:auto 1fr;
                              gap:0 10px; margin-bottom:5px; }
  .sungas-slip .pay-details .lbl { color:#64748b; }
  .sungas-slip .pay-details .val { font-weight:600; font-family:monospace; }
  .sungas-slip .footer { font-size:6.5pt; color:#94a3b8; text-align:center;
                          margin-top:4px; border-top:1px solid #e2e8f0; padding-top:3px;
                          line-height:1.3; }
</style>

<div class="sungas-slip">

  <!-- HEADER -->
  <div class="hdr">
    <h1>{{ doc.company }}</h1>
    <div class="hdr-sub">Payslip for {{ period_label }}</div>
    <div class="hdr-meta">
      Slip #{{ doc.name }} &nbsp;|&nbsp;
      Pay Date: {{ frappe.utils.formatdate(doc.posting_date, "dd MMM yyyy") }}
    </div>
  </div>

  <!-- EMPLOYEE + PERIOD -->
  <div class="grid-2">
    <div>
      <h2>Employee</h2>
      <div class="row"><span class="lbl">Name</span>     <span class="val">{{ doc.employee_name }}</span></div>
      <div class="row"><span class="lbl">Staff ID</span> <span class="val">{{ doc.employee }}</span></div>
      <div class="row"><span class="lbl">Dept</span>     <span class="val">{{ doc.department or "—" }}</span></div>
      <div class="row"><span class="lbl">Role</span>     <span class="val">{{ doc.designation or "—" }}</span></div>
      <div class="row"><span class="lbl">Branch</span>   <span class="val">{{ doc.branch or "—" }}</span></div>
      {% if emp.grade_level %}
      <div class="row"><span class="lbl">Grade</span>    <span class="val">{{ emp.grade_level }}</span></div>
      {% endif %}
    </div>
    <div>
      <h2>Pay Period</h2>
      <div class="row"><span class="lbl">Start</span>    <span class="val">{{ frappe.utils.formatdate(doc.start_date, "dd MMM yyyy") }}</span></div>
      <div class="row"><span class="lbl">End</span>      <span class="val">{{ frappe.utils.formatdate(doc.end_date, "dd MMM yyyy") }}</span></div>
    </div>
  </div>

  <!-- EARNINGS + DEDUCTIONS side-by-side -->
  <div class="ed-grid">
    <div>
      <h2>Earnings</h2>
      <table class="tbl">
        {% set ns_earn = namespace(rows=0) %}
        {% for e in doc.earnings %}
          {% if not e.statistical_component and not e.do_not_include_in_total and (e.amount or 0) > 0 %}
            {% set ns_earn.rows = ns_earn.rows + 1 %}
            <tr class="tbl-row">
              <td>{{ e.salary_component }}</td>
              <td class="amt">{{ "{:,.2f}".format(e.amount or 0) }}</td>
            </tr>
          {% endif %}
        {% endfor %}
        {% if ns_earn.rows == 0 %}
          <tr class="tbl-row"><td colspan="2" style="color:#94a3b8;font-style:italic;">No earnings.</td></tr>
        {% endif %}
        <tr class="tbl-total">
          <td>Gross Pay</td>
          <td class="amt">{{ "{:,.2f}".format(doc.gross_pay or 0) }}</td>
        </tr>
      </table>
    </div>

    <div>
      <h2>Deductions</h2>
      <table class="tbl">
        {% set ns_ded = namespace(rows=0) %}
        {% for d in doc.deductions %}
          {% if not d.statistical_component and not d.do_not_include_in_total and (d.amount or 0) > 0 %}
            {% set ns_ded.rows = ns_ded.rows + 1 %}
            <tr class="tbl-row">
              <td>{{ d.salary_component }}</td>
              <td class="amt">{{ "{:,.2f}".format(d.amount or 0) }}</td>
            </tr>
          {% endif %}
        {% endfor %}
        {% if doc.total_loan_repayment and doc.total_loan_repayment > 0 %}
          <tr class="tbl-row">
            <td>Total Loan</td>
            <td class="amt">{{ "{:,.2f}".format(doc.total_loan_repayment) }}</td>
          </tr>
          {% set ns_ded.rows = ns_ded.rows + 1 %}
        {% endif %}
        {% if ns_ded.rows == 0 %}
          <tr class="tbl-row"><td colspan="2" style="color:#94a3b8;font-style:italic;">No deductions.</td></tr>
        {% endif %}
        <tr class="tbl-total">
          <td>Total Deduction</td>
          <td class="amt">{{ "{:,.2f}".format((doc.total_deduction or 0) + (doc.total_loan_repayment or 0)) }}</td>
        </tr>
      </table>
    </div>
  </div>

  <!-- NET PAY -->
  <div class="net-box">
    <span class="lbl">Net Pay</span>
    <span class="val">NGN {{ "{:,.2f}".format(doc.net_pay or 0) }}</span>
  </div>
  {% if doc.total_in_words %}
    <div class="words"><em>{{ doc.total_in_words }}</em></div>
  {% endif %}

  <!-- EMPLOYER CONTRIBUTIONS (statistical / company-paid) -->
  {% set has_stat = [] %}
  {% for e in doc.earnings %}{% if e.statistical_component and (e.amount or 0) > 0 %}{% set _ = has_stat.append(1) %}{% endif %}{% endfor %}
  {% for d in doc.deductions %}{% if d.statistical_component and (d.amount or 0) > 0 %}{% set _ = has_stat.append(1) %}{% endif %}{% endfor %}
  {% if has_stat %}
  <div class="stat-block">
    <h2>Employer Contributions (not deducted from Net)</h2>
    <table>
      {% for e in doc.earnings %}
        {% if e.statistical_component and (e.amount or 0) > 0 %}
        <tr>
          <td>{{ e.salary_component }}</td>
          <td class="amt">{{ "{:,.2f}".format(e.amount or 0) }}</td>
        </tr>
        {% endif %}
      {% endfor %}
      {% for d in doc.deductions %}
        {% if d.statistical_component and (d.amount or 0) > 0 %}
        <tr>
          <td>{{ d.salary_component }}</td>
          <td class="amt">{{ "{:,.2f}".format(d.amount or 0) }}</td>
        </tr>
        {% endif %}
      {% endfor %}
    </table>
  </div>
  {% endif %}

  <!-- PAYMENT DETAILS -->
  {% if doc.bank_name or doc.bank_account_no %}
  <div class="pay-details">
    {% if doc.bank_name %}
      <span class="lbl">Bank:</span><span class="val" style="font-family:inherit;">{{ doc.bank_name }}</span>
    {% endif %}
    {% if doc.bank_account_no %}
      {% set acct = doc.bank_account_no | string %}
      {% set masked = "•••••• " + acct[-4:] if acct|length >= 4 else acct %}
      <span class="lbl">Account:</span><span class="val">{{ masked }}</span>
    {% endif %}
    {% if doc.mode_of_payment %}
      <span class="lbl">Mode:</span><span class="val" style="font-family:inherit;">{{ doc.mode_of_payment }}</span>
    {% endif %}
  </div>
  {% endif %}

  <div class="footer">
    Computer-generated payslip — no signature required. Queries: hr@sungas.ng
  </div>

</div>
"""


def upsert_print_format() -> None:
    name = FORMAT_NAME
    existed = frappe.db.exists("Print Format", name)
    print(f"  {'Updating' if existed else 'Creating'} Print Format: {name}")

    if existed:
        pf = frappe.get_doc("Print Format", name)
    else:
        pf = frappe.new_doc("Print Format")
        pf.name = name

    pf.doc_type             = "Salary Slip"
    pf.print_format_type    = "Jinja"
    pf.standard             = "No"      # critical: survives bench update
    pf.custom_format        = 1         # critical: use our Jinja (ignore doctype meta)
    pf.module               = "Custom"
    pf.disabled             = 0
    pf.html                 = PAYSLIP_HTML
    pf.font                 = "Default"
    pf.font_size            = 10
    pf.margin_top           = 8
    pf.margin_bottom        = 8
    pf.margin_left          = 8
    pf.margin_right         = 8
    pf.default_print_language = "en"
    pf.show_section_headings  = 0
    pf.line_breaks            = 0
    pf.absolute_value         = 0
    pf.align_labels_right     = 0

    pf.flags.ignore_permissions = True
    pf.save()
    frappe.db.commit()
    print(f"  + {name}: docstatus={pf.docstatus} standard={pf.standard} custom_format={pf.custom_format}")


def set_as_default() -> None:
    """Make 'Sungas Payslip' the default in Desk's Print dropdown for Salary Slip.

    Two layers required:
      1. Property Setter on Salary Slip.default_print_format -> controls the
         Desk Print dropdown default (what users actually see).
      2. Payroll Settings.salary_slip_print_format -> controls the format used
         when HRMS emails slips to employees.
    """
    # ---- 1. Property Setter (Desk Print dropdown default) ----
    ps_name = "Salary Slip-main-default_print_format"
    try:
        if frappe.db.exists("Property Setter", ps_name):
            ps = frappe.get_doc("Property Setter", ps_name)
            old = ps.value
            ps.value = FORMAT_NAME
            ps.flags.ignore_permissions = True
            ps.save()
        else:
            old = "<none>"
            ps = frappe.get_doc({
                "doctype":      "Property Setter",
                "name":         ps_name,
                "doctype_or_field": "DocType",
                "doc_type":     "Salary Slip",
                "property":     "default_print_format",
                "property_type": "Data",
                "value":        FORMAT_NAME,
            })
            ps.flags.ignore_permissions = True
            ps.insert()
        frappe.db.commit()
        # Bust the meta cache so the Print dropdown shows the new default immediately
        frappe.clear_cache(doctype="Salary Slip")
        print(f"  + Property Setter Salary Slip.default_print_format: {old!r} -> {FORMAT_NAME!r}")
    except Exception as e:
        print(f"  ! Could not set Property Setter ({e!r}). Set manually: ")
        print("    Desk -> Customize Form -> Salary Slip -> Default Print Format")

    # ---- 2. Payroll Settings (used when emailing slips) ----
    try:
        pset = frappe.get_single("Payroll Settings")
        old = pset.get("salary_slip_print_format") or ""
        if old != FORMAT_NAME:
            pset.salary_slip_print_format = FORMAT_NAME
            pset.flags.ignore_permissions = True
            pset.save()
            frappe.db.commit()
            print(f"  + Payroll Settings.salary_slip_print_format: {old!r} -> {FORMAT_NAME!r}")
        else:
            print(f"  = Payroll Settings already set to {FORMAT_NAME!r}")
    except Exception as e:
        print(f"  ! Could not set Payroll Settings ({e!r}).")


def main() -> None:
    print("=" * 72)
    print(f" Phase 6 / Step 6d -- Install Print Format: {FORMAT_NAME}")
    print("=" * 72)
    upsert_print_format()
    set_as_default()
    print()
    print("  Preview a slip:")
    print("  https://sungasmis.v.frappe.cloud/app/salary-slip/Sal Slip/HR-EMP-00002/00006/view/print")
    print(f"  Or pick any slip in Desk and Print -> select '{FORMAT_NAME}'.")
    print()
    print("  Upgrade safety:")
    print("    - standard='No', custom_format=1, module='Custom'")
    print("    - Frappe does NOT touch this record on bench update.")


# bench-execute scope-fix
try:
    _g = globals()
    for _k, _v in list(locals().items()):
        if _k not in _g:
            _g[_k] = _v
except Exception:
    pass

main()
