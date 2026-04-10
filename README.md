# Jivo Wellness - WhatsApp SAP B1 PO Approval Bot

A FastAPI service that integrates **SAP Business One (HANA)** with **WhatsApp (Meta Cloud API)** to enable Purchase Order approval/rejection directly from WhatsApp.

---

## How It Works

1. **Poll SAP HANA** every 10 seconds for pending approval rows (`OWDD` with `ProcesStat='W'`, `ObjType='22'`)
2. **Send WhatsApp template** to approvers with Approve / Reject quick-reply buttons + item details
3. **Receive button tap** via Meta webhook (`POST /webhook`)
4. **Update SAP HANA** tables (`OWDD`, `WDD1`, `ODRF`) with the approval decision
5. **Send confirmation** to the confirmation phone list

---

## Tech Stack

| Package        | Purpose                               |
|----------------|---------------------------------------|
| Python 3.12    | Runtime                               |
| FastAPI        | Async web framework                   |
| Uvicorn        | ASGI server                           |
| APScheduler    | Background polling (every 10 seconds) |
| hdbcli         | SAP HANA Python driver                |
| httpx          | HTTP client for Meta Cloud API        |
| Jinja2         | Dashboard HTML templates              |
| python-dotenv  | Environment variable management       |

---

## Project Structure

```
whatapp_bot/
├── main.py                  # FastAPI app entry point, scheduler setup
├── requirements.txt         # Python dependencies
├── .env                     # Environment variables (not in git)
├── test_hana.py             # Test SAP HANA connectivity
├── test_send.py             # Test WhatsApp template sending
├── templates/
│   └── dashboard.html       # Web dashboard template
├── logs/                    # Rotating log files (auto-created)
├── app/
│   ├── config.py            # Environment variable loading
│   ├── logging_setup.py     # Rotating file loggers (6 log files)
│   ├── poller.py            # HANA polling logic
│   ├── stats.py             # In-memory stats & activity feed
│   ├── db/
│   │   ├── connection.py    # HANA connection management
│   │   ├── queries.py       # SAP approval queries (OWDD, WDD1, ODRF)
│   │   └── tracking.py      # JIVO_WA_SENT tracking table
│   ├── whatsapp/
│   │   ├── constants.py     # Document type mappings (25+ types)
│   │   └── sender.py        # WhatsApp message sender functions
│   └── routes/
│       ├── webhook.py       # Meta webhook (verify + receive buttons)
│       ├── health.py        # GET /health endpoint
│       ├── test.py          # GET /test-wa, GET /test-items
│       ├── dashboard.py     # GET / — web dashboard
│       └── api.py           # GET /api/pending, POST /api/decide
```

---

## Setup

### 1. Clone & Create Virtual Environment

```bash
cd /home/superadmin/whatapp_bot
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables

Create a `.env` file in the project root:

```dotenv
# SAP HANA
HANA_HOST=<hana-server-ip>
HANA_PORT=30015
HANA_USER=<db-user>
HANA_PASS=<db-password>
HANA_SCHEMA=<schema-name>

# WhatsApp / Meta Cloud API
WA_ACCESS_TOKEN=<meta-access-token>
WA_PHONE_NUMBER_ID=<phone-number-id>
WA_BUSINESS_ACCOUNT_ID=<business-account-id>
WA_VERIFY_TOKEN=jivo_secure_123

# Phone Lists (comma-separated, international format without +)
APPROVER_PHONE=919876543210,919876543211        # Receives PO approval requests
CONFIRMATION_PHONE=919876543210                  # Receives confirmation/error messages

# Template Names (optional, have defaults)
WA_TEMPLATE_NAME=sap_approval_notification_v2
WA_CONFIRM_TEMPLATE=po_approval_confirmation_v2
WA_ERROR_TEMPLATE=sap_already_processed_v2
WA_ITEMS_TEMPLATE=po_information_v1
```

### 4. Run Locally

```bash
source .venv/bin/activate
uvicorn main:app --host 127.0.0.1 --port 5005 --workers 1 --log-level info
```

---

## Environment Variables Reference

| Variable               | Required | Default                    | Description                                    |
|------------------------|----------|----------------------------|------------------------------------------------|
| `HANA_HOST`            | Yes      | -                          | SAP HANA server IP/hostname                    |
| `HANA_PORT`            | Yes      | `30015`                    | SAP HANA port                                  |
| `HANA_USER`            | Yes      | -                          | Database username                              |
| `HANA_PASS`            | Yes      | -                          | Database password                              |
| `HANA_SCHEMA`          | Yes      | -                          | SAP schema name                                |
| `WA_ACCESS_TOKEN`      | Yes      | -                          | Meta Cloud API Bearer token                    |
| `WA_PHONE_NUMBER_ID`   | Yes      | -                          | WhatsApp Business phone number ID              |
| `APPROVER_PHONE`       | Yes      | -                          | Comma-separated approver phone numbers         |
| `CONFIRMATION_PHONE`   | Yes      | -                          | Comma-separated confirmation phone numbers     |
| `WA_VERIFY_TOKEN`      | No       | `jivo_secure_123`          | Webhook verification token                     |
| `WA_TEMPLATE_NAME`     | No       | `po_approval_request`      | Approval request template name                 |
| `WA_CONFIRM_TEMPLATE`  | No       | `new_template`             | Confirmation template name                     |
| `WA_ERROR_TEMPLATE`    | No       | `po_already_processed_v1`  | Error template name                            |
| `WA_ITEMS_TEMPLATE`    | No       | `po_item_details`          | Item details template name                     |

---

## Dual Phone List System

The bot uses two separate phone lists for different message types:

### APPROVER_PHONE
- Receives PO approval notifications with Approve/Reject buttons
- Receives per-item detail messages
- Templates: `sap_approval_notification_v2`, `po_information_v1`
- Use case: Approval managers / decision makers

### CONFIRMATION_PHONE
- Receives confirmation messages after approval/rejection
- Receives error/already-processed alerts
- Templates: `po_approval_confirmation_v2`, `sap_already_processed_v2`
- Use case: Finance teams, administrators, audit trail

### Message Flow

```
SAP HANA (pending PO)
  |
  v
Poller (every 10s)
  |
  v
send_whatsapp_approval() --> APPROVER_PHONE list
  |                           - sap_approval_notification_v2
  |                           - po_information_v1 (per item)
  v
User taps Approve/Reject
  |
  v
Webhook receives button tap
  |
  +-- PO already processed?
  |     YES --> send_error_message() --> CONFIRMATION_PHONE list
  |                                       - sap_already_processed_v2
  |
  |     NO --> apply_approval_decision() in SAP HANA
  |              |
  |              v
  |            send_confirmation_message() --> CONFIRMATION_PHONE list
  |                                            - po_approval_confirmation_v2
  v
Dashboard shows both phone lists
```

---

## API Endpoints

| Method | Path          | Description                                        |
|--------|---------------|----------------------------------------------------|
| GET    | `/`           | HTML dashboard (stats, logs, sent records, config) |
| GET    | `/health`     | JSON health check with config summary              |
| GET    | `/test-wa`    | Send test approval to all approver phones          |
| GET    | `/test-items` | Send test item detail to first approver            |
| GET    | `/api/pending`| Return pending POs as JSON for dashboard           |
| POST   | `/api/decide` | Approve/reject a PO from the dashboard             |
| GET    | `/webhook`    | Meta webhook verification handshake                |
| POST   | `/webhook`    | Receive WhatsApp button tap callbacks              |

### GET /health Response

```json
{
  "status": "running",
  "sent_count": 42,
  "time": "2026-03-26T10:30:00.000000",
  "hana_schema": "YOUR_SCHEMA",
  "approver_phones": ["919876543210", "919876543211"],
  "template": "sap_approval_notification_v2"
}
```

### GET /api/pending Response

```json
{
  "status": "ok",
  "data": [
    {
      "WddCode": 1234,
      "ObjType": "22",
      "BPName": "ABC Supplies",
      "PONumber": "PO-001",
      "TotalAmount": 1250,
      "CreatedBy": "John Doe"
    }
  ]
}
```

### POST /api/decide

Approve or reject a PO directly from the dashboard. Sends WhatsApp confirmation to CONFIRMATION_PHONES.

**Request:**
```json
{
  "wdd_code": 1234,
  "action": "APPROVE",
  "user": "Admin"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Approved successfully"
}
```

### Dashboard (GET /)

The web dashboard displays:
- **Stats grid**: Uptime, Messages Sent, Approvals, Rejections, Send Failures, Poll Cycles, Webhooks, HANA Errors
- **Configuration**: HANA host, schema, approver phones, confirmation phones, templates, phone ID
- **Recent Activity**: Last 50 events (polling & webhooks)
- **JIVO_WA_SENT table**: All tracking records with status badges (APPROVED / REJECTED / PENDING)
- **Log Viewer**: Tabbed view of last 100 lines from 6 log files
- Auto-refreshes every 30 seconds

---

## WhatsApp Cloud API

### Configuration

| Parameter        | Value                                                        |
|------------------|--------------------------------------------------------------|
| **Base URL**     | `https://graph.facebook.com/v19.0/{PHONE_NUMBER_ID}/messages`|
| **HTTP Method**  | `POST`                                                       |
| **Content-Type** | `application/json`                                           |
| **Auth Header**  | `Authorization: Bearer {WA_ACCESS_TOKEN}`                    |
| **HTTP Client**  | `httpx` (Python) with 10-second timeout                      |

### How to Get the Access Token

1. Go to [Meta for Developers](https://developers.facebook.com/)
2. Create or open your App
3. Navigate to **WhatsApp > API Setup**
4. Copy the **Temporary Access Token** (24 hours) or generate a **Permanent Token** via System Users

---

## WhatsApp Templates

All templates must be **pre-registered and approved** in Meta Business Manager before use.

### Template 1: PO Approval Request

| Field         | Value                           |
|---------------|---------------------------------|
| Template Name | `sap_approval_notification_v2`  |
| Category      | UTILITY                         |
| Language      | English (`en`)                  |
| Buttons       | 2 Quick Reply (Approve/Reject)  |

**Body:**
```
*Purchase Order Approval Request*

*WDD Code:* {{wdd_code}}
*Document Type:* {{doc_type}}
*Vendor:* {{vendor}}
*PO Number:* {{po_number}}
*Total Amount:* {{amount}}
*Raised By:* {{raised_by}}

*Item Details:*
{{items}}

Please review and take action.
```

**Parameters (7):**

| # | Name       | Description                           | Example            |
|---|------------|---------------------------------------|--------------------|
| 1 | wdd_code   | Unique WDD Code from SAP              | `"1234"`           |
| 2 | doc_type   | Human-readable document type          | `"Purchase Order"` |
| 3 | vendor     | Business Partner / Vendor name        | `"ABC Supplies"`   |
| 4 | po_number  | Purchase Order number                 | `"PO-2024-001"`    |
| 5 | amount     | Formatted total amount (no decimals)  | `"1,250"`          |
| 6 | raised_by  | Name of PO creator                    | `"John Doe"`       |
| 7 | items      | Summary of item count                 | `"3 item(s)"`      |

**Buttons:**

| Index | Label   | Type        | Payload              |
|-------|---------|-------------|----------------------|
| 0     | Approve | quick_reply | `APPROVE_{wdd_code}` |
| 1     | Reject  | quick_reply | `REJECT_{wdd_code}`  |

---

### Template 2: Item Details (Per Item)

One message per item - avoids character limits and works outside the 24-hour window.

| Field         | Value              |
|---------------|--------------------|
| Template Name | `po_information_v1`|
| Category      | UTILITY            |
| Language      | English (`en`)     |
| Buttons       | None               |

**Body:**
```
*Item Details*

*Code:* {{code}}
*Name:* {{name}}
*Demand Qty:* {{demand}}
*In Stock:* {{instock}}
*Benchmark:* {{benchmark}}
```

**Parameters (5):**

| # | Name      | Description                         | Example            |
|---|-----------|-------------------------------------|--------------------|
| 1 | code      | Item code from SAP                  | `"ITM-001"`        |
| 2 | name      | Item name / description             | `"Steel Bolts M10"`|
| 3 | demand    | PO quantity (formatted with commas) | `"100"`            |
| 4 | instock   | Current stock level                 | `"500"`            |
| 5 | benchmark | Minimum stock / benchmark           | `"200"`            |

---

### Template 3: Approval Confirmation

Sent to CONFIRMATION_PHONE list after approval/rejection is recorded.

| Field         | Value                          |
|---------------|--------------------------------|
| Template Name | `po_approval_confirmation_v2`  |
| Category      | UTILITY                        |
| Language      | English (`en`)                 |
| Buttons       | None                           |

**Body:**
```
*PO Action Confirmed*

*WDD Code:* {{wdd_code}}
*PO Number:* {{po_number}}
*Document Type:* {{doc_type}}
*Vendor:* {{vendor}}
*Total Amount:* {{amount}}
*Raised By:* {{raised_by}}

*Action:* {{action}}
*Time:* {{time}}

This action has been successfully recorded in SAP.
```

**Parameters (8):**

| # | Name       | Description                          | Example                       |
|---|------------|--------------------------------------|-------------------------------|
| 1 | wdd_code   | Unique WDD Code from SAP             | `"1234"`                      |
| 2 | po_number  | Purchase Order number                | `"PO-2024-001"`               |
| 3 | doc_type   | Human-readable document type         | `"Purchase Order"`            |
| 4 | vendor     | Business Partner / Vendor name       | `"ABC Supplies"`              |
| 5 | amount     | Formatted total amount (no decimals) | `"1,250"`                     |
| 6 | raised_by  | Name of PO creator                   | `"John Doe"`                  |
| 7 | action     | Action taken                         | `"APPROVED"` or `"REJECTED"`  |
| 8 | time       | Timestamp of action                  | `"24 Mar 2026, 10:30 AM"`     |

---

### Template 4: Already Processed (Error)

Sent to CONFIRMATION_PHONE list when someone tries to act on an already-processed PO.

| Field         | Value                     |
|---------------|---------------------------|
| Template Name | `sap_already_processed_v2`|
| Category      | UTILITY                   |
| Language      | English (`en`)            |
| Buttons       | None                      |

**Body:**
```
*Action Failed*

PO with WDD Code *{{wdd_code}}* has already been *{{current_status}}*.

Your attempt to *{{attempted_action}}* this PO could not be processed.

*Time:* {{time}}

Please contact the admin if you need further assistance.
```

**Parameters (4):**

| # | Name             | Description                          | Example                       |
|---|------------------|--------------------------------------|-------------------------------|
| 1 | wdd_code         | WDD Code number                      | `"1234"`                      |
| 2 | current_status   | Already applied status               | `"APPROVED"` or `"REJECTED"` |
| 3 | attempted_action | Action the user tried                | `"APPROVE"` or `"REJECT"`    |
| 4 | time             | Timestamp                            | `"24 Mar 2026, 10:30 AM"`    |

---

## API Call Examples

### Send Approval Request

```bash
curl -X POST "https://graph.facebook.com/v19.0/{PHONE_NUMBER_ID}/messages" \
  -H "Authorization: Bearer {ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "messaging_product": "whatsapp",
    "to": "919876543210",
    "type": "template",
    "template": {
      "name": "sap_approval_notification_v2",
      "language": { "code": "en" },
      "components": [
        {
          "type": "body",
          "parameters": [
            { "type": "text", "parameter_name": "wdd_code", "text": "1234" },
            { "type": "text", "parameter_name": "doc_type", "text": "Purchase Order" },
            { "type": "text", "parameter_name": "vendor", "text": "ABC Supplies" },
            { "type": "text", "parameter_name": "po_number", "text": "PO-001" },
            { "type": "text", "parameter_name": "amount", "text": "1,250" },
            { "type": "text", "parameter_name": "raised_by", "text": "John Doe" },
            { "type": "text", "parameter_name": "items", "text": "3 item(s)" }
          ]
        },
        {
          "type": "button", "sub_type": "quick_reply", "index": "0",
          "parameters": [{ "type": "payload", "payload": "APPROVE_1234" }]
        },
        {
          "type": "button", "sub_type": "quick_reply", "index": "1",
          "parameters": [{ "type": "payload", "payload": "REJECT_1234" }]
        }
      ]
    }
  }'
```

### Send Item Details

```bash
curl -X POST "https://graph.facebook.com/v19.0/{PHONE_NUMBER_ID}/messages" \
  -H "Authorization: Bearer {ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "messaging_product": "whatsapp",
    "to": "919876543210",
    "type": "template",
    "template": {
      "name": "po_information_v1",
      "language": { "code": "en" },
      "components": [
        {
          "type": "body",
          "parameters": [
            { "type": "text", "parameter_name": "code", "text": "ITM-001" },
            { "type": "text", "parameter_name": "name", "text": "Steel Bolts M10" },
            { "type": "text", "parameter_name": "demand", "text": "100" },
            { "type": "text", "parameter_name": "instock", "text": "500" },
            { "type": "text", "parameter_name": "benchmark", "text": "200" }
          ]
        }
      ]
    }
  }'
```

### Meta API Success Response

```json
{
  "messaging_product": "whatsapp",
  "contacts": [{ "input": "919876543210", "wa_id": "919876543210" }],
  "messages": [{ "id": "wamid.HBgLMTIzNDU2Nzg5MBUCABI..." }]
}
```

---

## Webhook

### Verification (GET /webhook)

Meta sends a GET request to verify your webhook URL during setup.

| Parameter          | Description                                  |
|--------------------|----------------------------------------------|
| `hub.mode`         | Always `"subscribe"`                         |
| `hub.verify_token` | Must match your `WA_VERIFY_TOKEN`            |
| `hub.challenge`    | Random string from Meta - echo it back       |

### Receive Button Click (POST /webhook)

**Button type payload:**
```json
{
  "entry": [{
    "changes": [{
      "field": "messages",
      "value": {
        "messages": [{
          "from": "919876543210",
          "type": "button",
          "button": { "text": "Approve", "payload": "APPROVE_1234" }
        }]
      }
    }]
  }]
}
```

**Interactive type payload** (some WhatsApp clients):
```json
{
  "entry": [{
    "changes": [{
      "field": "messages",
      "value": {
        "messages": [{
          "from": "919876543210",
          "type": "interactive",
          "interactive": {
            "type": "button_reply",
            "button_reply": { "id": "APPROVE_1234", "title": "Approve" }
          }
        }]
      }
    }]
  }]
}
```

**Webhook response codes:**

| Scenario               | Response                             |
|------------------------|--------------------------------------|
| Successfully processed | `{"status": "ok"}`                   |
| Already processed PO   | `{"status": "already_processed"}`    |
| Status updates         | `{"status": "ignored - no messages"}`|
| Non-button message     | `{"status": "ignored - type {type}"}`|

> Always return 200 OK to Meta. Non-200 responses cause Meta to retry delivery.

---

## Meta API Error Codes

| Code   | Subcode | Meaning                           | Fix                                    |
|--------|---------|-----------------------------------|----------------------------------------|
| 100    | 2494073 | Template parameter count mismatch | Ensure all parameters are provided     |
| 100    | 2494072 | Template not found / not approved | Check template name and approval status|
| 131030 | -       | Rate limit hit                    | Retry with backoff                     |
| 131047 | -       | Re-engagement (>24 hr, no tmpl)   | Use template messages                  |
| 190    | -       | Invalid/expired access token      | Refresh your access token              |
| 368    | -       | Blocked for policy violations     | Review Meta Business policies          |

### Parameter Sanitization

Meta rejects template parameters with newlines, tabs, or 4+ consecutive spaces. All parameters are auto-sanitized before sending.

---

## SAP HANA Database

### Tables Used

| Table          | Operation | Purpose                                    |
|----------------|-----------|--------------------------------------------|
| `OWDD`         | SELECT    | Get pending approvals (`ProcesStat='W'`)   |
| `OWDD`         | UPDATE    | Set `ProcesStat` to `Y` (approve) or `N` (reject) |
| `WDD1`         | UPDATE    | Set approval status, date, time, remarks   |
| `ODRF`         | UPDATE    | Set `WddStatus='A'` on approve only       |
| `JIVO_WA_SENT` | ALL       | Track which POs have been sent via WhatsApp|
| `view_whatsapp_bot` | SELECT | Custom view for pending approvals with item details |

### JIVO_WA_SENT Tracking Table

Auto-created on startup.

```sql
CREATE TABLE "SCHEMA"."JIVO_WA_SENT" (
    "WddCode"   INTEGER      NOT NULL PRIMARY KEY,
    "SentAt"    TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    "Status"    NVARCHAR(20) DEFAULT 'PENDING'
)
```

| Status    | Meaning                                         |
|-----------|-------------------------------------------------|
| `PENDING` | Approval message sent, awaiting response        |
| `APPROVE` | Approver tapped Approve and SAP was updated     |
| `REJECT`  | Approver tapped Reject and SAP was updated      |

### Document Type Mapping

| ObjType Code | Document Type              |
|-------------|----------------------------|
| `22`        | Purchase Order              |
| `540000006` | Purchase Quotation          |
| `20`        | Goods Receipt PO            |
| `1470000113`| Goods Returns Request       |
| `21`        | Goods Returns               |
| `204`       | A/P Down Payment            |
| `18`        | A/P Invoice                 |
| `19`        | A/P Credit Memo             |
| `112`       | Purchase Request            |
| `1250000001`| Internal Requisition        |
| `23`        | Sales Quotation             |
| `17`        | Sales Order                 |
| `15`        | Delivery                    |
| `13`        | A/R Invoice                 |
| `14`        | A/R Credit Memo             |
| `203`       | A/R Down Payment            |
| `59`        | Goods Receipt               |
| `60`        | Goods Issue                 |
| `67`        | Inventory Transfer          |
| `67001`     | Inventory Transfer Request  |
| `69`        | Inventory Opening Balance   |
| `165`       | Inventory Counting          |
| `163`       | Inventory Posting           |
| `24`        | Incoming Payment            |
| `46`        | Outgoing Payment            |

---

## Logging System

Six rotating log files under `logs/` directory (5 MB max, 10 backups each):

| File           | Content                           |
|----------------|-----------------------------------|
| `app.log`      | General application events        |
| `error.log`    | Errors only (WARNING+)            |
| `webhook.log`  | Webhook events and payloads       |
| `whatsapp.log` | WhatsApp API send/receive results |
| `poll.log`     | Polling cycle events              |
| `hana.log`     | SAP HANA database operations      |

```bash
# View logs in real-time
tail -f logs/app.log
tail -f logs/webhook.log
tail -f logs/whatsapp.log
tail -f logs/poll.log
```

---

## Systemd Service (Optional)

Create a systemd unit file at `/etc/systemd/system/whatsapp_bot.service` to run the bot as a service.

### Commands

```bash
sudo systemctl daemon-reload
sudo systemctl enable whatsapp_bot
sudo systemctl start whatsapp_bot       # Start
sudo systemctl stop whatsapp_bot        # Stop
sudo systemctl restart whatsapp_bot     # Restart
sudo systemctl status whatsapp_bot      # Status
sudo journalctl -u whatsapp_bot -f      # Journal logs
```

---

## Flow Diagram

```
+----------------------------------------------------------------------+
|                        OUTGOING FLOW (Polling)                        |
|                                                                       |
|  SAP HANA                    Bot Server                   WhatsApp    |
|                                                                       |
|  view_whatsapp_bot --poll--> poll_and_send()                          |
|  (pending POs)         every 10s                                      |
|                              |                                        |
|                              +- Check JIVO_WA_SENT (skip if sent)     |
|                              |                                        |
|                              +- FOR EACH approver phone:              |
|                              |  +- Send template ----POST--------->   |
|                              |  |  (approval request)      Approver   |
|                              |  |                          sees PO    |
|                              |  |                          + buttons  |
|                              |  |                                     |
|                              |  +- FOR EACH item:                     |
|                              |     +- Send template ---POST------->   |
|                              |        (item details)       Approver   |
|                              |                             sees items |
|                              +- Mark in JIVO_WA_SENT (PENDING)        |
|                                                                       |
+-----------------------------------------------------------------------+
|                        INCOMING FLOW (Webhook)                        |
|                                                                       |
|  WhatsApp                    Bot Server                   SAP HANA    |
|                                                                       |
|  Approver taps               POST /webhook                            |
|  [Approve] or  ---POST----> |                                        |
|  [Reject]                   +- Parse payload                          |
|                             |  (APPROVE_1234 or REJECT_1234)          |
|                             |                                         |
|                             +- Check current status ---SELECT-------> |
|                             |                          OWDD table     |
|                             |                                         |
|                             +- If already processed:                  |
|                             |  +- Send error to CONFIRMATION_PHONE    |
|                             |     (already_processed template)        |
|                             |                                         |
|                             +- If pending (ProcesStat='W'):           |
|                             |  +- Update OWDD ---UPDATE-------------> |
|                             |  +- Update WDD1 ---UPDATE-------------> |
|                             |  +- Update ODRF ---UPDATE-------------> |
|                             |  |  (only on APPROVE)                   |
|                             |  +- Update JIVO_WA_SENT ---UPDATE-----> |
|                             |  |  (Status -> APPROVE or REJECT)       |
|                             |  +- Send confirm to CONFIRMATION_PHONE  |
|                             |     (confirmation template)             |
|                             |                                         |
|                             +- Return 200 OK to Meta                  |
+-----------------------------------------------------------------------+
|                        MONITORING ENDPOINTS                           |
|                                                                       |
|  Browser  --GET /----------->  Dashboard (HTML)                       |
|           --GET /health----->  JSON status                            |
|           --GET /test-wa---->  Send test approval to all approvers    |
|           --GET /test-items->  Send test item template                |
+-----------------------------------------------------------------------+
```

---

## All API Calls Summary

| # | Direction | Template / Type                  | When                                | Recipient          |
|---|-----------|----------------------------------|-------------------------------------|---------------------|
| 1 | Outgoing  | `sap_approval_notification_v2`   | New pending PO found during polling | APPROVER_PHONE      |
| 2 | Outgoing  | `po_information_v1` (x N items)  | Immediately after #1, one per item  | APPROVER_PHONE      |
| 3 | Incoming  | Webhook POST (button payload)    | Approver taps Approve/Reject        | -                   |
| 4 | Outgoing  | `po_approval_confirmation_v2`    | After successful approve/reject     | CONFIRMATION_PHONE  |
| 5 | Outgoing  | `sap_already_processed_v2`       | When PO was already processed       | CONFIRMATION_PHONE  |
| 6 | Incoming  | Webhook GET (verification)       | One-time during Meta webhook setup  | -                   |

---

## Remaining Improvements (TODO)

The Medium and Low priority items below have been implemented. The following Critical and High items are still pending:

### Critical

| # | Issue | File |
|---|-------|------|
| 1.1 | Remove `.env` from git history, rotate credentials | `.env` |
| 1.2 | Validate `X-Hub-Signature-256` on incoming webhooks | `app/routes/webhook.py` |

### High

| # | Issue | File |
|---|-------|------|
| 2.1 | Wrap blocking HANA calls with `asyncio.to_thread()` | `app/routes/webhook.py`, `api.py`, `dashboard.py` |
| 2.3 | Require `WA_VERIFY_TOKEN` via env (no weak default) | `app/config.py` |
| 2.4 | Add CORS middleware with explicit allowed origins | `main.py` |
| 2.5 | Add authentication to dashboard or hide sensitive config | `app/routes/dashboard.py` |
