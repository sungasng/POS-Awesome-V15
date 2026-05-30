# Sungas Engagement App — Integration Credentials Checklist

**Sprint 0 deliverable** — please verify each item with your IT / vendor accounts and tick what you have. Empty cells = please provision.

---

## 1. Twilio (WhatsApp Business API) 🟢

Twilio is the brief's chosen WhatsApp BSP. Outbound to customers, inbound webhook to our app.

| # | Item | Status | Source / where to find it |
|---|---|---|---|
| 1.1 | Twilio Account SID (starts `AC...`) | ☐ | Twilio Console → Account Dashboard |
| 1.2 | Twilio Auth Token | ☐ | Twilio Console → Account Dashboard (rotatable) |
| 1.3 | **Verified WhatsApp Sender** phone number (`whatsapp:+234...`) | ☐ | Twilio Console → Messaging → Senders → WhatsApp |
| 1.4 | WhatsApp Business Profile **approved** by Meta (not in sandbox) | ☐ | Profile must show "Approved" — sandbox numbers don't work in production |
| 1.5 | **Message Templates** approved by Meta (English at minimum) | ☐ | Need at least: Order Confirmation, Delivery Status, Ticket Acknowledgement, Engagement Outreach, Feedback Request |
| 1.6 | Webhook URL configured (will be `https://sungasmis.v.frappe.cloud/api/method/scl_engagement.whatsapp.inbound`) | ☐ | Set this after we deploy Phase D |
| 1.7 | Twilio account billing in **Production** mode (not Trial) | ☐ | Trial accounts can only message verified numbers |
| 1.8 | Monthly message volume estimate shared with Twilio (for rate limit upgrade) | ☐ | Default tier: 250 msgs/sec; we likely need 1k+/sec for bulk campaigns |

**What you should send me when ready:**
```
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_WHATSAPP_FROM=whatsapp:+234...
TWILIO_MESSAGING_SERVICE_SID=MG... (optional but recommended)
```

---

## 2. Termii (SMS gateway) 🟢

Termii is the brief's chosen Nigeria-local SMS provider. Bulk + transactional SMS.

| # | Item | Status | Source / where to find it |
|---|---|---|---|
| 2.1 | Termii API Key | ☐ | Termii Dashboard → API Settings → Live API Key (not Sandbox) |
| 2.2 | Approved **Sender ID** (e.g., `SUNGAS`) | ☐ | Termii Dashboard → Senders → must be "Approved" by Nigerian regulators |
| 2.3 | Inbound number for STOP / opt-out keyword (optional but recommended) | ☐ | Termii Dashboard → Short Codes |
| 2.4 | Account credit balance > ₦20,000 minimum for testing | ☐ | Termii Dashboard → Wallet |
| 2.5 | DLR (Delivery Receipt) webhook configured | ☐ | Set this after we deploy Phase D — URL will be `.../api/method/scl_engagement.sms.dlr` |
| 2.6 | NDPC / NCC compliance: each promotional SMS must offer "Reply STOP to opt out" | ☐ | We'll bake this into the outbound template |

**What you should send me when ready:**
```
TERMII_API_KEY=...
TERMII_SENDER_ID=SUNGAS
TERMII_BASE_URL=https://api.ng.termii.com  (or v3 endpoint they assigned)
```

---

## 3. Brevo (Sendinblue) — Email 🟢

Brevo (formerly Sendinblue) for transactional + marketing emails.

| # | Item | Status | Source / where to find it |
|---|---|---|---|
| 3.1 | Brevo SMTP API v3 Key | ☐ | Brevo Dashboard → SMTP & API → API Keys → "Generate a new API key" |
| 3.2 | Verified **sender domain** (e.g., `sungas.org`) with DKIM + SPF passing | ☐ | Brevo Dashboard → Senders → Domains → must show "Authenticated" |
| 3.3 | Verified sender email addresses (e.g., `noreply@sungas.org`, `hr@sungas.org`, `dpo@sungas.org`) | ☐ | Brevo Dashboard → Senders → Email Senders |
| 3.4 | Inbound parsing webhook configured (for incoming emails → Interaction Log) | ☐ | Brevo Dashboard → Inbound Parsing → URL will be `.../api/method/scl_engagement.email.inbound` |
| 3.5 | Brevo account plan supports your expected volume (Free tier = 300/day; we likely need Business or higher) | ☐ | Brevo Dashboard → Plan & Billing |
| 3.6 | Transactional email templates created (optional — we can do this in code) | ☐ | Order Confirmation, Ticket Acknowledgement, Feedback Request, Engagement Plan Outcome |

**What you should send me when ready:**
```
BREVO_API_KEY=xkeysib-...
BREVO_SENDER_EMAIL=noreply@sungas.org
BREVO_SENDER_NAME=Sungas Company Limited
BREVO_INBOUND_DOMAIN=mail.sungas.org  (subdomain you point MX to Brevo)
```

---

## 4. Frappe Cloud bench config (we'll inspect these together) 🟢

| # | Item | What we'll check |
|---|---|---|
| 4.1 | Background worker count | `bench config get-common-config -g background_workers` |
| 4.2 | Worker queue split | Check `Procfile` for `default`, `short`, `long`, `mail` queues |
| 4.3 | Site config secrets storage | Confirm `site_config.json` is not in git |
| 4.4 | Backup schedule | `bench --site sungasmis.v.frappe.cloud schedule-backups` |
| 4.5 | Mail outbound (system emails, error reports) | Already configured? |

No action from you — I'll inspect and report.

---

## 5. Future-phase placeholders (NOT needed for Sprint 0)

| Integration | Status | Action |
|---|---|---|
| **3CX Phone System** | ☐ | Phase D+. When ready, we'll need: 3CX URL, API key, extension list |
| **LMS (Last-Mile Delivery)** | ☐ | Phase D+. When the LMS vendor is selected, we'll exchange API specs |
| **Stripe (online payments)** | ☐ | Already partly set up. Activation pending. |

---

## 6. Storage in Frappe (where credentials live)

For each integration we'll create a dedicated **Single DocType**:

- `WhatsApp Configuration` — stores Twilio creds (1.1–1.4) as Password fields
- `SMS Configuration` — stores Termii creds (2.1, 2.2) as Password fields
- `Brevo Email Configuration` — stores Brevo creds (3.1–3.3) as Password fields

Password-type fields are encrypted at rest in MariaDB (`fernet` symmetric encryption tied to `encryption_key` in `site_config.json`). They are masked in the UI and in error logs (per the developer brief §Security).

**Never** put credentials in `.env`, in code, or in a commit. Always via the Single DocType UI.

---

## How to send credentials to me

When you have any/all of the above, send them via:

1. **Preferred:** create the Single DocType records yourself in Desk after Phase A is deployed. I don't see the values.
2. **Pre-deployment:** if you want me to seed them, paste in this chat — I'll insert them and **redact them from chat history** after deployment.

---

**Last updated:** Sprint 0  
**Owner:** Engagement App implementation
