# Phase 5.7 — POS Hardening (Pre-Engagement App Sprint)

**Goal:** prevent the v13 "POS breaks after 6 months" failure pattern from repeating on v15.

**Duration:** ~1 week (4 deployable scripts + 1 audit report).

---

## Runbook

Execute these in sequence on the bench. Each is idempotent — safe to re-run.

### Step 1 — Audit (read-only)

```bash
SHA=<pinned commit>
curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/$SHA/scripts/p57_step1_audit.py" -o /tmp/p57a.py
bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/p57a.py').read())"
```

What it tells you:
- A. Idempotency on background submit (✓ already good)
- B. Stock oversell risk (gap; mitigation in step 3)
- C. Shift-close-with-queue mismatch (gap; fix in step 4)
- D. Stuck invoice monitoring (gap; fix in step 5)
- E. Composite indexes on hot tables (likely missing on Sales Invoice)
- F. Stock Ledger Entry row count + projected annual growth

Output: `/tmp/p57_pos_audit.md`

### Step 2 — Add composite indexes

```bash
curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/$SHA/scripts/p57_step2_indexes.py" -o /tmp/p57b.py
bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/p57b.py').read())"
```

Adds 5 composite indexes. Run during low traffic — each `CREATE INDEX` on a big table is a 5-30s blocking operation. Reduces POS List View load time from "minutes at scale" to <500ms.

### Step 3 — Stock oversell mitigation (POS Awesome source patch)

**Manual code patch — coming in next commit.** Will be a 20-line edit to `submit_in_background_job` in `posawesome/api/invoices.py`:
- Wrap the `_validate_stock_on_invoice` + `submit()` block in `frappe.db.savepoint("posa_submit")` and a `SELECT ... FOR UPDATE` row lock on the warehouse-item bin record.
- Retry up to 3 times on `pymysql.err.OperationalError` 1213 (deadlock).
- On final failure, raise so the existing exception handler logs + notifies.

### Step 4 — POS Closing Entry pre-check

```bash
curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/$SHA/scripts/p57_step4_closing_precheck.py" -o /tmp/p57d.py
# First run in audit mode:
bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/p57d.py').read())"
# If no surprises, flip to enforce:
sed -i "s/^CHECK_MODE       = 'audit'/CHECK_MODE       = 'enforce'/" /tmp/p57d.py
bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/p57d.py').read())"
```

Installs a Server Script (`POS Closing -- Block On Stale Drafts`, `is_standard=No`) that throws a clear error if the cashier tries to close a shift with queued invoices still Draft.

### Step 5 — Stuck invoice monitor

```bash
curl -fsSL "https://raw.githubusercontent.com/sungasng/POS-Awesome-V15/$SHA/scripts/p57_step5_stuck_monitor.py" -o /tmp/p57e.py
# Dry-run to see what would be retried:
bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/p57e.py').read())"
# To execute retries:
sed -i 's/^DRY_RUN                 = True$/DRY_RUN                 = False/' /tmp/p57e.py
bench --site sungasmis.v.frappe.cloud execute "exec(open('/tmp/p57e.py').read())"
```

After verifying behaviour:
- Wire it into `hooks.py` as a `*/5 * * * *` scheduled job
- Add to POS Health Dashboard (next step)

### Step 6 — POS Health Dashboard (Frappe Workspace)

**Coming in next commit.** Single-page workspace with the following number cards:
- Stuck POS invoices (Draft >10 min, last 24h)
- Stale POS Closing Entries (Draft >24h)
- Same-second concurrent sales (oversell candidates, last 7d)
- Background job failure count (last 24h)
- SLE row count vs 6-month-ago baseline

### Step 7 — SLE consolidation cron

**Coming in next commit.** Adds `frappe.utils.background_jobs.consolidate_stock_ledger_entries` to `scheduler_events` (weekly on Sunday 2 AM). Keeps Stock Balance report fast.

### Step 8 — Synthetic load test

**Coming after step 7.** A script that replays a synthetic 6-month sales pattern (50K invoices across the 22 POS profiles) into a sandbox bench and measures:
- Median List View load time
- P95 invoice submission latency
- SLE growth rate
- Slow query log

Pass threshold: all queries <200ms, no slow log entries.

---

## What the v13 "month 6 break" actually looked like

For context — the failure modes we're hardening against:

| Symptom (v13) | Root cause | Mitigation (v15) |
|---|---|---|
| POS List View takes 45s to load | No index on `(pos_profile, posting_date, docstatus)`; full table scan | Step 2 |
| "Last cylinder" sold by 3 cashiers simultaneously, oversold by 2 units | Race condition: `validate_stock` reads, `submit` writes, no lock | Step 3 |
| Cashier closes shift, ₦80K shortfall, reverses 2 days later when queued invoices finally submit | Closing Entry tallies submitted invoices; queue hadn't flushed | Step 4 |
| 14 Draft invoices found by Finance 3 weeks after creation | Worker died mid-submit, job not requeued, nobody noticed | Step 5 |
| Stock Balance report times out at 5 min | 500K SLE rows accumulated, no consolidation | Step 7 |
| Whole bench restarts daily | OOM from a single bad scheduled job loading entire Sales Invoice list | Step 6 dashboard + code review every scheduled job |

---

**Last updated:** Sprint 5.7
