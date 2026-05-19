# 10 — Disaster Recovery & Backup

How Sungas survives data loss, accidental deletion, ransomware, or Frappe Cloud
infrastructure outage.

## What Frappe Cloud gives you out of the box

| Layer | Built-in protection |
|---|---|
| Database backups | Automatic daily, 7-day retention |
| File storage | Mirrored across availability zones |
| App code | Pinned to Git commit SHA in Bench config |
| TLS certs | Auto-renewed via Let's Encrypt |
| OS patches | Auto-applied during maintenance windows |
| Snapshot before update | Auto-taken before any "Update Apps" |

> Default tier of Frappe Cloud is **NOT** suitable for the production Sungas
> bench. Upgrade to **Production** plan for 28-day backup retention + SLA.

## What we add on top

### Layer 1: Off-site database snapshot (weekly)

Run every Sunday via cron on an Admin laptop:

```bash
#!/bin/bash
# weekly_db_backup.sh
SITE=sungasmis.v.frappe.cloud
TODAY=$(date +%Y%m%d)
BACKUP_DIR=~/sungas-backups
mkdir -p $BACKUP_DIR

# Trigger a fresh backup (Frappe Cloud admin panel button equivalent)
curl -X POST "https://${SITE}/api/method/frappe.utils.backups.backup" \
  -H "Authorization: token <API_KEY>:<API_SECRET>" \
  -H "Content-Type: application/json"

sleep 30  # Wait for backup to finish

# Download the latest backup from Frappe Cloud's S3 URL
# (Get URL from Frappe Cloud Dashboard > Site > Backups > Download)
# Then encrypt with gpg before storing
```

> Frappe Cloud doesn't expose SSH or direct DB access on managed sites.
> Use the admin Dashboard to manually download `.sql.gz` weekly to encrypted USB
> until automation is built. Off-site = different cloud provider (Google Drive
> Workspace, S3-compatible) — encrypted at rest.

### Layer 2: GitHub source of truth

Every customization is in Git:
- App code → `sungasng/Sungas`, `sungasng/HR-Enhancements`, `sungasng/POS-Awesome-V15`
- Scripts → `scripts/` in this repo
- Print formats → committed via custom app fixtures
- Server Scripts → exported via `scripts/export_server_scripts.py` (TODO)

If the Frappe Cloud site is unrecoverable: spin up a new bench, install all 3
apps from the pinned Git SHA, restore DB from off-site backup, done.

### Layer 3: Fixture exports (monthly)

Export Sungas-specific config that isn't in code:

```bash
bench --site sungasmis.v.frappe.cloud export-fixtures
```

Targets (set in `hooks.py` of `sungas` app):
- Custom Fields (Employee, POS Profile, Item, Customer)
- Property Setters
- Server Scripts
- Print Formats
- Workflow definitions
- Workflow State / Action
- Custom DocPerm rules
- LPG Outlet Price Tier (the entire 64-row matrix)
- Role Profiles

These export to `sungas/sungas/fixtures/<doctype>.json` and commit to Git.
Reload via `bench migrate` (auto-imports).

## Recovery scenarios

### Scenario 1: Accidental deletion of a customer

**Likelihood**: High.

**Recovery**: ERPNext keeps a `Deleted Document` for 7 days.
- `Setup > Deleted Document > List` → find → Restore.

### Scenario 2: Accidental cancellation of submitted SSA / Sales Invoice

**Likelihood**: Medium.

**Recovery**: Cancelled docs remain in DB.
- Open the cancelled doc, click "Amend" — creates a new draft with same data,
  re-submit.

### Scenario 3: Mass-edit script ran with wrong filter

**Likelihood**: Medium (this is why we DRY_RUN first).

**Recovery**: 
- If within 24h → restore from last day's backup, replay POS sales from
  POS Invoice log between backup time and disaster.
- If > 24h → painful manual fix.

> **Prevention**: Every script in `/scripts/` has `DRY_RUN=True` default.
> Cardinal rule: review dry-run output BEFORE flipping to False.

### Scenario 4: Frappe Cloud has multi-hour outage

**Likelihood**: Low (Frappe Cloud uptime ≥ 99.9%).

**Recovery**: Wait. SLA covers credits.

**Mitigation for cashiers during outage**:
- Cashiers fall back to manual receipts (Sungas Branded receipt pad — pre-printed pads).
- Daily lodgement to bank as normal.
- When ERP back: enter sales via Sales Invoice (not POS Invoice — can backdate).
- Post-recovery audit: match physical receipts to system entries.

### Scenario 5: Hostile takeover / ransomware on Frappe Cloud

**Likelihood**: Very low. Frappe Cloud is hardened.

**Recovery**:
- Last off-site encrypted backup (Layer 1) restored to alternative ERPNext install.
- New domain, communicate to users, force password reset for all.
- Estimated downtime: 24-48h depending on backup freshness.

### Scenario 6: All custom apps' GitHub repos deleted

**Likelihood**: Very low (multi-user PAT-protected).

**Recovery**:
- Frappe Cloud bench has a working clone of each app — copy back to GitHub.
- Maintain a third-party mirror (e.g., GitLab) updated weekly via CI.

## Backup verification (do this monthly)

Don't trust backups you haven't tested. Once a month:

1. Download latest Frappe Cloud backup.
2. Spin up local Frappe instance:
   ```bash
   bench new-site test-restore.local
   bench --site test-restore.local restore /path/to/backup.sql.gz \
     --with-public-files /path/to/files.tar \
     --with-private-files /path/to/private.tar
   ```
3. Login as Administrator.
4. Verify:
   - [ ] Today's POS Invoice count matches production
   - [ ] Employee count (217+) matches
   - [ ] Item Price for `LPG-REFILL` matches production
5. Destroy test instance.
6. Log result in `docs/dr/backup-verification.log`.

## Password & secret management

| Secret | Where stored | Rotation |
|---|---|---|
| Administrator password | Password manager (1Password / Bitwarden) — Sungas IT vault | Quarterly |
| GitHub PAT | Encrypted in 1Password | Per-task (don't reuse) |
| API keys (any 3rd party) | Frappe Doctype `API Key` — encrypted at rest | Quarterly |
| User passwords | Bcrypt hashed in DB | User-managed |
| Frappe Cloud account | Password manager + 2FA mandatory | Quarterly |

> All PATs from the bench setup phase MUST be revoked once Phase 6 is complete.

## Incident response checklist

When an incident occurs:

1. **STOP** — don't change anything. Take screenshots.
2. **NOTIFY** — IT lead + Head of Finance immediately.
3. **CONTAIN** — disable affected user(s), block bench writes if needed.
4. **DIAGNOSE** — Activity Log, Error Log, Stock Ledger.
5. **CLASSIFY**:
   - P0: Data loss / financial fraud → activate DR plan immediately.
   - P1: Service down / multi-user impact → escalate to Frappe Cloud support.
   - P2: Single-user issue → fix in-line, document.
6. **DOCUMENT** — incident log in `docs/incidents/YYYY-MM-DD-summary.md`.

## Contacts

| Need | Contact |
|---|---|
| Frappe Cloud Support | `support@frappe.io` or in-dashboard chat |
| Sungas IT Lead | [Email/phone] |
| Sungas Head of Finance | [Email/phone] |
| MD (escalation) | [Email/phone] |

## Recovery time objectives (RTO)

| Scenario | RTO target | RPO (max data loss) |
|---|---|---|
| Single doc deletion | 5 min | 0 |
| Single outlet outage | 1 hour | 0 |
| Full site outage | 4 hours | < 24h |
| Total disaster (restore from backup) | 24 hours | < 7 days |

## Annual DR drill

Once a year, run a full restore-and-verify exercise. Document outcome.
Update this manual based on findings.
