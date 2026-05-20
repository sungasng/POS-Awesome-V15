# HR Team — ERPNext Migration Checklist & Templates

**Purpose**: Step-by-step handover for the HR team to migrate day-to-day
activities onto ERPNext after Phase 6 (HRMS Configuration) goes live.

**Target go-live**: 25 June 2026 (parallel payroll run 23 June).

**Owner**: Head of HR + supporting Officers.

---

## A. Pre go-live (target: complete by 18 June 2026)

### A1. Grade Level Review (P0 — blocks Leave Allocation)

- [ ] Receive `grade_mapping_for_hr.csv` from IT
- [ ] HR reviews each row; corrects `proposed_grade` for misclassified staff
- [ ] Pay extra attention to G6 defaults — anyone senior accidentally caught?
- [ ] Save edits, return to IT for upload via `apply_grade_overrides.py`
- [ ] Verify final grades in `HR > Employee > List` — group by Grade Level

### A2. Employee Records Audit (P0)

- [ ] Verify 217 active employees + 4 Okhuoromi unknowns resolved
  - DOMINION ROLAND, BULUS SATI, GODWIN SAVIOUR, ISAAC ONWUZULUIGBO
- [ ] Confirm each Employee has:
  - [ ] Correct `date_of_joining` (drives anniversary benefits)
  - [ ] Correct `branch` (drives Cost Center routing + Holiday List)
  - [ ] Correct `department` (drives leave approval workflow)
  - [ ] Correct `designation` (drives Grade Level + CC routing)
  - [ ] `state_of_residence` (NTAA 2025 PAYE jurisdiction)
  - [ ] `payroll_cost_center` (Operations/Sales/HQ routing)

### A3. Bank Details Verification (P0 for payroll)

- [ ] Each Employee has:
  - [ ] Bank name, account number, account name
  - [ ] BVN (for compliance)
  - [ ] Confirmation that account is in employee's name

Template: `HR-001-Bank-Details-Confirmation.docx` (see Templates section).

### A4. HMO Records (P1)

- [ ] Decide HMO coverage per employee:
  - [ ] `hmo_coverage_type`: Basic / Standard / Family
  - [ ] `hmo_monthly_premium_company_paid` (benchmark ₦)
  - [ ] `hmo_monthly_topup_staff_paid` (if any)
- [ ] Verify against company's group HMO policy contract

### A5. Rent Declaration (P1 — affects PAYE)

- [ ] Distribute `HR-002-Rent-Declaration.docx` (see Templates)
- [ ] Collect signed declarations from staff who pay annual rent
- [ ] Update `Employee.rent_paid_annually` per employee
- [ ] **Default is ₦0 if not declared** (conservative — staff over-pays PAYE,
       reclaims at year-end FIRS filing)

### A6. Leave Balances Migration (P1)

- [ ] For any staff with carried-over leave from 2025:
  - [ ] Compute days remaining as at 31 Mar 2026 (Q1 grace period)
  - [ ] Create manual `Leave Allocation` doctype entry per employee
       (since handbook policy: forfeit after Q1)
- [ ] For staff in mid-probation:
  - [ ] Confirm date_of_joining is correct (drives 6-month annual leave wait)

### A7. Onboarding Form Standardization (P2)

- [ ] Replace any existing onboarding forms with the new ones (Templates section)
- [ ] Train HR Officers to use ERPNext `Employee` directly for new hires

---

## B. Go-live week (23–25 June 2026)

### B1. Parallel Payroll Run (23 June) — IT-led, HR validates

- [ ] IT generates June ERP payslips for all 213+ employees
- [ ] HR cross-checks **10 random employees** against Excel:
  - 2× G1/G2 (Director, Head)
  - 2× G3/G4 (Manager, Supervisor)
  - 4× G5/G6 (Officer, Cashier)
  - 2× edge cases (probationer, anniversary month)
- [ ] Pass criteria: difference < ₦100 on every payslip
- [ ] Sign off: `Payroll Reconciliation Sign-off Sheet` (Templates section)

### B2. June Payroll Submission (25 June)

- [ ] Plant Managers approve Leave Applications for June
- [ ] HR Manager submits Payroll Entry for June 2026
- [ ] HR Manager submits Salary Slips (bulk)
- [ ] Finance runs Payment Entry against Bank Account
- [ ] Confirm Bank Upload File generated (Phase 6 / Step 6)
- [ ] Send bank upload to Finance for processing
- [ ] After bank confirmation: mark Salary Slips as Paid

### B3. PAYE / Pension Remittance (by 30 June)

- [ ] Generate PAYE report: `HR > Salary Register > group by state_of_residence`
- [ ] Pay each state IRS by their deadline (most: 10th of next month)
- [ ] Generate Pension report: total Employee + Employer contributions
- [ ] Remit to each employee's RSA via PFA (within 7 days of salary payment)

### B4. NSITF / HMO Remittance (by 5 July)

- [ ] NSITF: 1% of gross to NSITF by 5 July
- [ ] HMO premium: per-employee batch to HMO provider

---

## C. Monthly cycle (recurring, starting July 2026)

### C1. Monthly Cycle Calendar

| Day | Activity | Owner |
|---|---|---|
| 1st of month | Open new Leave Period (auto via system) | System |
| 15th | Send draft payroll preview to Plant Managers | HR Manager |
| 18th | Plant Managers confirm attendance + leave taken | Plant Mgrs |
| 20th | HR runs Payroll Entry for current month | HR Manager |
| 22nd | HR Manager + Head of Finance review variance | HR + HoF |
| 23rd | Finance approves bank upload | Head of Finance |
| 25th | Salaries hit employee bank accounts | Finance |
| End-of-month | Stat remittance (PAYE, Pension, NSITF) | HR + Finance |

### C2. Leave Management Cycle

- [ ] Employee files Leave Application via Self-Service
- [ ] Line Manager approves/rejects within 24h
- [ ] HR Manager second-approves Maternity/Compassionate/Unpaid
- [ ] Auto-deducted from leave balance on approval
- [ ] Q1 of following year: HR runs `Leave Forfeiture` report and emails staff

### C3. Anniversary Tracking

- [ ] HR runs Auto-Email Report: "Upcoming Anniversaries (next 60 days)"
- [ ] For each upcoming anniversary:
  - [ ] Verify Leave Allowance fires correctly in their month's payslip
  - [ ] Update Long Service Award status (5/10/15/20/25/30 years)

### C4. Exit Procedures

When an employee leaves:
- [ ] Update `Employee.status = Left`
- [ ] Set `Employee.relieving_date`
- [ ] Compute final entitlements (pro-rated leave, 13th month pro-rata if before Dec)
- [ ] Generate exit gratuity (if applicable) via Additional Salary
- [ ] Generate final payslip
- [ ] Issue Service Certificate from `HR > Service Certificate` doctype
- [ ] Update User account: `enabled = 0`
- [ ] Hand over POS Profile reassignment to Plant Manager

---

## D. Quarterly cycle

- [ ] **Q1**: Forfeit prior year's unused Annual Leave (handbook rule)
- [ ] **Q1**: Issue P9 / annual PAYE certificate to each employee
- [ ] **Q1**: Submit FIRS annual employer return (Form A)
- [ ] **Q2**: Performance reviews → may trigger grade changes → update grade_level
- [ ] **Q3**: HMO policy renewal review
- [ ] **Q4**: 13th Month decision by management → toggle eligibility if needed
- [ ] **Q4**: Pension reconciliation with each PFA

---

## E. Annual cycle

- [ ] **December**: 13th Month payout (auto via salary slip if toggle on)
- [ ] **December**: Long Service Awards ceremony — pull list from HR
- [ ] **December**: Year-end Group Life Insurance renewal (Pension Reform Act 2014)
- [ ] **January**: New Leave Period auto-creates; Leave Allocations roll
- [ ] **January**: Annual increment review (if any) → update SSAs
- [ ] **March**: Forfeit unused 2025 carry-over (handbook)

---

## F. Templates

### Template 1: `HR-001-Bank-Details-Confirmation.docx`

> **EMPLOYEE BANK DETAILS CONFIRMATION**
>
> Date: ____________________
>
> Employee ID: ____________________
> Employee Name: ____________________
>
> Bank Name: ____________________
> Account Number: ____________________
> Account Name (as on bank record): ____________________
> BVN: ____________________
>
> I confirm the above account is in my name and authorise Sungas Company Limited
> to remit monthly salary into this account from June 2026 onwards.
>
> Employee Signature: ____________________
> Date: ____________________
>
> ----- For HR Use -----
> Verified by: ____________________
> ERP Updated: ☐ Yes  ☐ No
> Date Updated: ____________________

### Template 2: `HR-002-Rent-Declaration.docx`

> **ANNUAL RENT DECLARATION — NTAA 2025 RENT RELIEF**
>
> Pursuant to the Nigeria Tax Act 2025, employees who pay annual rent are
> entitled to a Rent Relief deduction (20% of declared rent, capped at ₦500,000).
>
> Employee ID: ____________________
> Employee Name: ____________________
> Tax Year: 2026
>
> I, ____________________ (full name), declare that I pay annual rent of
> ₦ ____________________ for my place of residence at:
>
> Address: ____________________
> ____________________
>
> I attach a copy of my current tenancy agreement / rent receipt.
>
> I understand:
> - Sungas will apply a Rent Relief of (20% × declared rent), capped at ₦500,000
> - This relief reduces my PAYE deduction
> - I may be required to produce supporting documents during FIRS audit
> - False declaration may result in disciplinary action
>
> Employee Signature: ____________________
> Date: ____________________
>
> ----- For HR Use -----
> Tenancy doc attached: ☐ Yes  ☐ No
> ERP `rent_paid_annually` updated: ☐ Yes
> Date Updated: ____________________

### Template 3: `HR-003-Leave-Application-Form.docx`

> **LEAVE APPLICATION**
>
> (Recommended: submit via ERPNext Self-Service — this paper form for emergency
> backup only.)
>
> Employee ID: ____________________
> Name: ____________________
> Department: ____________________
> Designation: ____________________
> Branch: ____________________
>
> Leave Type: ☐ Annual ☐ Sick ☐ Maternity ☐ Paternity ☐ Compassionate ☐ Casual
>
> From: ____________________
> To: ____________________
> Total Days: ____________________
> Half Day: ☐ Yes ☐ No
>
> Reason: ____________________________________________
>
> Relief Officer (covering during absence): ____________________
>
> Employee Signature: ____________________
> Date: ____________________
>
> ----- For Line Manager -----
> ☐ Approved   ☐ Rejected
> Reason: ____________________
> Line Manager Signature: ____________________
> Date: ____________________
>
> ----- For HR Manager (Maternity/Compassionate/Unpaid only) -----
> ☐ Approved   ☐ Rejected
> HR Manager Signature: ____________________
> Date: ____________________

### Template 4: `HR-004-New-Hire-Onboarding.docx`

> **NEW HIRE ONBOARDING — ERPNext Data Entry Form**
>
> Section 1: Personal
> - First Name, Middle Name, Last Name
> - Date of Birth
> - Gender
> - Marital Status
> - Nationality
> - State of Origin
> - **State of Residence** (drives PAYE jurisdiction)
> - NIN
> - Email (personal)
> - Phone
> - Home Address
>
> Section 2: Employment
> - Date of Joining
> - Employment Type: ☐ Permanent ☐ Contract ☐ Probation
> - Probation End Date (if applicable)
> - Designation
> - **Grade Level (G1-G7)**
> - Department
> - Branch
> - Reporting Manager
> - **Payroll Cost Center**
>
> Section 3: Compensation
> - Monthly Gross Salary (₦)
> - Salary Structure: ☐ Sungas Standard ☐ Other ____________
> - Effective From: ____________________
>
> Section 4: Banking
> - Bank, Account #, BVN (use Template 1 for sign-off)
> - Tax Identification Number (TIN)
> - Pension Fund Administrator (PFA)
> - Pension Number (RSA PIN)
>
> Section 5: HMO
> - HMO Coverage Type: ☐ Basic ☐ Standard ☐ Family
> - Dependents: ____________
>
> Section 6: Annual Rent (Optional, for PAYE Rent Relief)
> - Annual Rent (₦): ____________________
>
> ----- For HR -----
> ☐ Personal Info entered in ERP
> ☐ Salary Structure Assignment created
> ☐ User account created with role profile
> ☐ POS Profile updated (if Cashier/Plant Manager)
> ☐ Onboarding Buddy assigned
> ☐ Equipment issued (laptop/phone/uniform)

### Template 5: `HR-005-Exit-Clearance.docx`

> **EXIT CLEARANCE FORM**
>
> Employee ID: ____________________
> Name: ____________________
> Department / Branch: ____________________
> Last Working Day: ____________________
>
> Section 1: Outstanding Items (signed off by relevant officer)
>
> | Item | Officer | Cleared (Y/N) | Date | Signature |
> |---|---|---|---|---|
> | Outstanding Loan | Finance Manager | | | |
> | Cooperative Balance | Cooperative Officer | | | |
> | Laptop / Equipment | IT Manager | | | |
> | ID Card / Access | Security | | | |
> | Uniform | Stores | | | |
> | Outstanding Annual Leave | Line Manager | | | |
>
> Section 2: Final Settlement (calculated by HR)
>
> | Item | Amount (₦) |
> |---|---:|
> | Salary up to last working day | |
> | Outstanding Annual Leave (encashment) | |
> | Pro-rated 13th Month (if applicable) | |
> | Gratuity (per handbook tenure) | |
> | LESS: Outstanding Loan | |
> | LESS: Outstanding Cooperative | |
> | **NET FINAL SETTLEMENT** | |
>
> Section 3: Sign-offs
> - HR Manager: ____________________
> - Head of Finance: ____________________
> - MD/COO: ____________________
> - Employee: ____________________
>
> ----- ERP Actions -----
> ☐ Employee status -> Left
> ☐ Relieving date set
> ☐ Final Salary Slip generated
> ☐ Additional Salary for gratuity created
> ☐ Service Certificate issued
> ☐ User account disabled
> ☐ POS Profile reassigned (if applicable)

---

## G. Training plan for HR team

| Session | Audience | Topic | Duration |
|---|---|---|---|
| 1 | All HR | ERPNext Desk navigation, Employee doctype | 2h |
| 2 | HR Mgr | Payroll Entry, Salary Slip generation, bulk operations | 3h |
| 3 | HR Mgr | Leave Management (workflow, approvals, reports) | 2h |
| 4 | HR Officers | New Hire data entry (using Template 4) | 2h |
| 5 | All HR | Reports — Salary Register, Leave Balance, Anniversaries | 2h |
| 6 | HR Mgr + HoF | Year-end procedures (13th month, leave forfeiture) | 2h |

Total: **13 hours** spread across 2 weeks pre go-live.

---

## H. Escalation contacts

| Issue | Owner | Phone/Email |
|---|---|---|
| Payroll discrepancy | HR Manager → Head of Finance | [tbd] |
| Leave workflow not firing | HR Manager → IT | [tbd] |
| Salary slip can't generate | IT (Frappe Cloud) | [tbd] |
| Stat remittance error | Head of Finance | [tbd] |
| HMO claim issue | HR Officer → HMO Account Mgr | [tbd] |

---

_Last updated: 2026-05-20 (Phase 6 / Step 4 finalized)._
_Owner: HR Lead. Edit via Pull Request to keep in version control._
