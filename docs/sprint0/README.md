# Sprint 0 — Engagement App Pre-Build Deliverables

Three documents for your review before we cut a single line of code on the Engagement App.

| Document | What it is | Action you need to take |
|---|---|---|
| [`privacy-policy-v1.0.md`](./privacy-policy-v1.0.md) | NDPA-compliant Privacy Policy template | Send to your legal counsel; fill in **[INSERT]** placeholders; sign off on final v1.0 |
| [`credentials-checklist.md`](./credentials-checklist.md) | Twilio + Termii + Brevo + Frappe Cloud bench requirements | Walk through each row with your IT vendor; report which are ✅ / ❌ / not yet provisioned |
| [`approval-matrix-schema.md`](./approval-matrix-schema.md) | DocType design for configurable approval thresholds | Review the 10 default thresholds; adjust amounts; answer the 5 open questions at the bottom |

## Why Sprint 0 matters

The brief is ~20 weeks of build. Skipping the upfront design questions means rework in week 12 when:

- Legal blocks go-live because the Privacy Policy wasn't drafted early
- WhatsApp templates aren't Meta-approved (10-day lead time)
- Finance discovers the threshold values are wrong after the first month's expenses
- A processor (e.g., Twilio) needs a Data Processing Agreement that takes 3 weeks to negotiate

All three deliverables are **independent** — your legal team can review the Privacy Policy while your IT vendor checks credentials while Finance reviews thresholds. Total wall-clock to complete this sprint: **1–2 weeks** if you parallelise.

## Definition of Done for Sprint 0

- [ ] Privacy Policy v1.0 signed off by Sungas legal, effective date set
- [ ] All Twilio / Termii / Brevo credentials confirmed available (or provisioning in progress with ETA)
- [ ] Approval matrix defaults approved by Finance Head + COO
- [ ] Roles confirmed (new `SCL ...` prefix or map to existing ERPNext roles)
- [ ] Frappe Cloud bench config (worker count, queues) confirmed

Once these are all green I cut the new `scl_engagement` app branch and start Phase A.

---

## Quick links

- Brief original: `SCL_Frappe_Developer_Brief_v1.1_3.docx` (uploaded 2026-05)
- Phase 5/6 work: see `/app/memory/PRD.md`
- POS Hardening proposal: pending decision (Sprint pre-A or parallel)
