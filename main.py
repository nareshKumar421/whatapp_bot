# ─────────────────────────────────────────────────────────────────────────────
# Jivo Wellness — WhatsApp SAP B1 PO Approval Service
# FastAPI + APScheduler + SAP HANA (hdbcli) + Meta Cloud API
#
# Flow:
#   1. Poll HANA every 60s for OWDD rows with ProcesStat='W', ObjType='22'
#   2. Send WhatsApp template message with Approve / Reject quick-reply buttons
#   3. Receive button tap via Meta webhook POST /webhook
#   4. Update OWDD, WDD1, ODRF in SAP HANA
#   5. Send confirmation message back to approver
# ─────────────────────────────────────────────────────────────────────────────

import os
from datetime import datetime
from typing import Optional

import httpx
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from hdbcli import dbapi

load_dotenv()
app = FastAPI(title="Jivo WA Approval", version="1.0.0")


# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────

HANA_HOST       = os.getenv("HANA_HOST")
HANA_PORT       = int(os.getenv("HANA_PORT", 30015))
HANA_USER       = os.getenv("HANA_USER")
HANA_PASS       = os.getenv("HANA_PASS")
HANA_SCHEMA     = os.getenv("HANA_SCHEMA")

WA_TOKEN        = os.getenv("WA_ACCESS_TOKEN")
WA_PHONE_ID     = os.getenv("WA_PHONE_NUMBER_ID")
APPROVER_PHONE  = os.getenv("APPROVER_PHONE")
TEMPLATE_NAME   = os.getenv("WA_TEMPLATE_NAME",    "po_approval_request")
CONFIRM_TMPL    = os.getenv("WA_CONFIRM_TEMPLATE", "po_approval_confirmation")
VERIFY_TOKEN    = os.getenv("WA_VERIFY_TOKEN",     "jivo_secure_123")

# In-memory set — avoids re-sending on same run
_already_sent: set[int] = set()


# ─────────────────────────────────────────────────────────────────────────────
# HANA HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def get_conn() -> dbapi.Connection:
    """Open and return a HANA connection."""
    return dbapi.connect(
        address=HANA_HOST,
        port=HANA_PORT,
        user=HANA_USER,
        password=HANA_PASS
    )


def t(table: str) -> str:
    """Return schema-qualified quoted table name. e.g. t('OWDD') → "JIVOTEST"."OWDD" """
    return f'"{HANA_SCHEMA}"."{table}"'


# ─────────────────────────────────────────────────────────────────────────────
# TRACKING TABLE
# Creates JIVO_WA_SENT in HANA to persist sent state across restarts
# ─────────────────────────────────────────────────────────────────────────────

def create_tracking_table():
    """Create JIVO_WA_SENT table if it does not exist."""
    conn = get_conn()
    cur  = conn.cursor()
    try:
        cur.execute(f"""
            CREATE TABLE {t("JIVO_WA_SENT")} (
                "WddCode"   INTEGER      NOT NULL PRIMARY KEY,
                "SentAt"    TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
                "Status"    NVARCHAR(20) DEFAULT 'PENDING'
            )
        """)
        conn.commit()
        print("✓ Created JIVO_WA_SENT tracking table.")
    except Exception as e:
        if "already exists" in str(e).lower():
            print("✓ JIVO_WA_SENT table already exists.")
        else:
            print(f"⚠ Table create warning: {e}")
    finally:
        cur.close()
        conn.close()


def load_sent_from_hana():
    """Load already-sent WddCodes into memory to avoid re-sending on restart."""
    conn = get_conn()
    cur  = conn.cursor()
    try:
        cur.execute(f'SELECT "WddCode" FROM {t("JIVO_WA_SENT")}')
        for row in cur.fetchall():
            _already_sent.add(row[0])
        print(f"✓ Loaded {len(_already_sent)} already-sent WddCodes from HANA.")
    except Exception as e:
        print(f"⚠ Could not load sent codes: {e}")
    finally:
        cur.close()
        conn.close()


def mark_as_sent(wdd_code: int):
    """Record WddCode in memory + HANA tracking table."""
    _already_sent.add(wdd_code)
    conn = get_conn()
    cur  = conn.cursor()
    try:
        cur.execute(f"""
            INSERT INTO {t("JIVO_WA_SENT")} ("WddCode", "SentAt", "Status")
            VALUES (?, CURRENT_TIMESTAMP, 'PENDING')
        """, (wdd_code,))
        conn.commit()
    except Exception:
        pass  # Already exists — fine
    finally:
        cur.close()
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# QUERY 1 — Fetch pending approvals from SAP B1
# Tables: OWDD (approval header) + WDD1 (approver step) +
#         OUSR (users) + ODRF (draft document)
# ─────────────────────────────────────────────────────────────────────────────

def get_pending_approvals() -> list[dict]:
    """
    Returns all Purchase Order approval requests currently waiting (ProcesStat='W').
    Mirrors ApprovalReader.GetPendingApprovals() from the C# service.
    """
    conn = get_conn()
    cur  = conn.cursor()
    try:
        cur.execute(f"""
            SELECT
                w."WddCode",
                w."DraftEntry",
                w."ObjType",
                w."OwnerID",
                w1."UserID"        AS "ApproverID",
                u."U_NAME"         AS "ApproverName",
                u."E_Mail"         AS "ApproverEmail",
                creator."U_NAME"   AS "CreatedBy",
                d."CardName"       AS "BPName",
                d."DocTotal"       AS "TotalAmount",
                d."Comments"
            FROM {t("OWDD")} w
            INNER JOIN {t("WDD1")} w1
                ON  w."WddCode"  = w1."WddCode"
            INNER JOIN {t("OUSR")} u
                ON  w1."UserID"  = u."USERID"
            INNER JOIN {t("OUSR")} creator
                ON  w."OwnerID"  = creator."USERID"
            LEFT  JOIN {t("ODRF")} d
                ON  w."DraftEntry" = d."DocEntry"
                AND w."ObjType"    = d."ObjType"
            WHERE w."ProcesStat"  = 'W'
              AND w1."Status"     = 'W'
              AND w."Status"     <> 'Y'
              AND w."ObjType"     = '22'
        """)
        # Remove the AND clause above and add below to filter by creator:
        # AND creator."U_NAME" = 'manager'

        cols = [col[0] for col in cur.description]
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        return rows
    finally:
        cur.close()
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# QUERY 2 — Check current status of a single WddCode
# Called before applying decision to avoid double-processing
# ─────────────────────────────────────────────────────────────────────────────

def get_wdd_status(wdd_code: int) -> Optional[dict]:
    """
    Returns OWDD row for given WddCode, or None if not found.
    Mirrors the SELECT check in HandleSubmit() from ApprovalWebServer.cs.
    """
    conn = get_conn()
    cur  = conn.cursor()
    try:
        cur.execute(f"""
            SELECT "WddCode", "ProcesStat", "DraftEntry", "ObjType"
            FROM   {t("OWDD")}
            WHERE  "WddCode" = {wdd_code}
        """)
        row = cur.fetchone()
        if not row:
            return None
        return {
            "WddCode":    row[0],
            "ProcesStat": row[1],
            "DraftEntry": row[2],
            "ObjType":    row[3]
        }
    finally:
        cur.close()
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# QUERY 3 + 4 — Apply approve / reject decision to SAP B1
# Updates OWDD (header) + WDD1 (approver step) + ODRF (draft, approve only)
# Mirrors HandleSubmit() in ApprovalWebServer.cs
# ─────────────────────────────────────────────────────────────────────────────

def apply_approval_decision(wdd_code: int, action: str,
                             remarks: str = "") -> dict:
    """
    action must be 'APPROVE' or 'REJECT'.
    Returns {"success": bool, "message": str}.
    """
    wdd = get_wdd_status(wdd_code)

    if wdd is None:
        return {"success": False, "message": f"WddCode {wdd_code} not found in SAP."}

    if wdd["ProcesStat"] != "W":
        return {
            "success": False,
            "message": f"Already processed. Current status: {wdd['ProcesStat']}"
        }

    new_status    = "Y" if action == "APPROVE" else "N"
    remark_text   = remarks if remarks else (
        "Approved via WhatsApp." if action == "APPROVE" else "Rejected via WhatsApp."
    )
    approval_date = datetime.now().strftime("%Y-%m-%d")
    approval_time = int(datetime.now().strftime("%H%M"))
    draft_entry   = wdd["DraftEntry"]

    conn = get_conn()
    cur  = conn.cursor()
    try:
        # QUERY 3a — Update OWDD approval header ─────────────────────────────
        cur.execute(f"""
            UPDATE {t("OWDD")}
            SET "ProcesStat" = ?,
                "Status"     = ?,
                "Remarks"    = ?
            WHERE "WddCode"  = ?
        """, (new_status, new_status, remark_text, wdd_code))
        conn.commit()

        # QUERY 3b — Update WDD1 approver step ───────────────────────────────
        cur.execute(f"""
            UPDATE {t("WDD1")}
            SET "Status"     = ?,
                "UpdateDate" = ?,
                "UpdateTime" = ?,
                "Remarks"    = ?
            WHERE "WddCode"  = ?
              AND "Status"  IN ('P', 'W')
        """, (new_status, approval_date, approval_time, remark_text, wdd_code))
        conn.commit()

        # QUERY 4 — Update ODRF draft status (approve only) ──────────────────
        if action == "APPROVE":
            cur.execute(f"""
                UPDATE {t("ODRF")}
                SET "WddStatus" = 'A'
                WHERE "DocEntry" = ?
            """, (draft_entry,))
            conn.commit()

        # Update tracking table status ────────────────────────────────────────
        cur.execute(f"""
            UPDATE {t("JIVO_WA_SENT")}
            SET "Status" = ?
            WHERE "WddCode" = ?
        """, (action, wdd_code))
        conn.commit()

        print(f"✓ WddCode={wdd_code} {action}D in SAP B1.")
        return {
            "success": True,
            "message": f"WddCode={wdd_code} {action}D successfully."
        }

    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        print(f"✗ DB error for WddCode={wdd_code}: {e}")
        return {"success": False, "message": f"DB error: {str(e)}"}
    finally:
        cur.close()
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# ObjType → Document name map
# Mirrors MapDocType() in ApprovalReader.cs
# ─────────────────────────────────────────────────────────────────────────────

OBJ_TYPE_MAP: dict[str, str] = {
    # Purchasing
    "540000006":   "Purchase Quotation",
    "22":          "Purchase Order",
    "20":          "Goods Receipt PO",
    "1470000113":  "Goods Returns Request",
    "21":          "Goods Returns",
    "204":         "A/P Down Payment",
    "18":          "A/P Invoice",
    "19":          "A/P Credit Memo",
    "112":         "Purchase Request",
    "1250000001":  "Internal Requisition",
    # Sales
    "23":  "Sales Quotation",
    "17":  "Sales Order",
    "15":  "Delivery",
    "13":  "A/R Invoice",
    "14":  "A/R Credit Memo",
    "203": "A/R Down Payment",
    # Inventory
    "59":    "Goods Receipt",
    "60":    "Goods Issue",
    "67":    "Inventory Transfer",
    "67001": "Inventory Transfer Request",
    "69":    "Inventory Opening Balance",
    "165":   "Inventory Counting",
    "163":   "Inventory Posting",
    # Payments
    "24": "Incoming Payment",
    "46": "Outgoing Payment",
}

def map_doc_type(obj_type: str) -> str:
    return OBJ_TYPE_MAP.get(str(obj_type), f"Document (Type {obj_type})")


# ─────────────────────────────────────────────────────────────────────────────
# WHATSAPP — Send approval request message
# Template: po_approval_request
# Variables: {{1}} WddCode  {{2}} DocType  {{3}} Vendor
#            {{4}} Amount   {{5}} CreatedBy
# Buttons:   index 0 = Approve (payload APPROVE_{wdd_code})
#            index 1 = Reject  (payload REJECT_{wdd_code})
# ─────────────────────────────────────────────────────────────────────────────

def send_whatsapp_approval(approval: dict) -> bool:
    """Send approval request template message to approver."""
    wdd_code   = approval["WddCode"]
    bp_name    = approval.get("BPName")    or "N/A"
    amount     = approval.get("TotalAmount") or 0
    doc_type   = map_doc_type(approval.get("ObjType", "22"))
    created_by = approval.get("CreatedBy") or "N/A"

    url     = f"https://graph.facebook.com/v19.0/{WA_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WA_TOKEN}",
        "Content-Type":  "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to":   APPROVER_PHONE,
        "type": "template",
        "template": {
            "name":     TEMPLATE_NAME,
            "language": {"code": "en"},
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "parameter_name": "wdd_code",  "text": str(wdd_code)},
                        {"type": "text", "parameter_name": "doc_type",  "text": doc_type},
                        {"type": "text", "parameter_name": "vendor",    "text": bp_name},
                        {"type": "text", "parameter_name": "amount",    "text": f"{amount:,.0f}"},
                        {"type": "text", "parameter_name": "raised_by", "text": created_by},
                    ]
                },
                {
                    "type":      "button",
                    "sub_type":  "quick_reply",
                    "index":     "0",
                    "parameters": [{"type": "payload",
                                    "payload": f"APPROVE_{wdd_code}"}]
                },
                {
                    "type":      "button",
                    "sub_type":  "quick_reply",
                    "index":     "1",
                    "parameters": [{"type": "payload",
                                    "payload": f"REJECT_{wdd_code}"}]
                }
            ]
        }
    }
    try:
        resp = httpx.post(url, json=payload, headers=headers, timeout=10)
        success = resp.status_code == 200
        print(f"  {'✓' if success else '✗'} WA send WddCode={wdd_code}: "
              f"{resp.status_code} {resp.text}")
        return success
    except Exception as e:
        print(f"  ✗ WA send exception WddCode={wdd_code}: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# WHATSAPP — Send confirmation message after decision
# Template: po_approval_confirmation
# Variables: {{1}} WddCode  {{2}} DocType  {{3}} Action  {{4}} Timestamp
# ─────────────────────────────────────────────────────────────────────────────

def send_confirmation_message(to_phone: str, wdd_code: int,
                               action: str, doc_type: str,
                               success: bool):
    """Send confirmation template back to approver after they tap a button."""
    if not success:
        return  # Don't send on SAP errors — just log

    status_text = "APPROVED ✅" if action == "APPROVE" else "REJECTED ❌"
    time_str    = datetime.now().strftime("%d %b %Y, %I:%M %p")

    url     = f"https://graph.facebook.com/v19.0/{WA_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WA_TOKEN}",
        "Content-Type":  "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to":   to_phone,
        "type": "template",
        "template": {
            "name":     CONFIRM_TMPL,
            "language": {"code": "en"},
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "parameter_name": "wdd_code", "text": str(wdd_code)},
                        {"type": "text", "parameter_name": "doc_type", "text": doc_type},
                        {"type": "text", "parameter_name": "action",   "text": status_text},
                        {"type": "text", "parameter_name": "time",     "text": time_str},
                    ]
                }
            ]
        }
    }
    try:
        resp = httpx.post(url, json=payload, headers=headers, timeout=10)
        print(f"  {'✓' if resp.status_code == 200 else '✗'} "
              f"Confirmation sent to {to_phone}: {resp.status_code}")
    except Exception as e:
        print(f"  ✗ Confirmation send error: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# POLLER — Runs every 60 seconds via APScheduler
# ─────────────────────────────────────────────────────────────────────────────

def poll_and_send():
    """Fetch pending PO approvals from HANA and send WhatsApp messages."""
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Polling HANA...")
    try:
        approvals = get_pending_approvals()
        new_ones  = [a for a in approvals if a["WddCode"] not in _already_sent]
        print(f"  Found {len(approvals)} pending | {len(new_ones)} new to send.")

        for approval in new_ones:
            wdd_code = approval["WddCode"]
            bp       = approval.get("BPName") or "N/A"
            amount   = approval.get("TotalAmount") or 0
            doc_type = map_doc_type(approval.get("ObjType", "22"))

            print(f"  → Sending WddCode={wdd_code} | {doc_type} | {bp} | ₹{amount:,.0f}")
            sent = send_whatsapp_approval(approval)

            if sent:
                mark_as_sent(wdd_code)
            else:
                print(f"  ✗ Will retry WddCode={wdd_code} on next poll.")

    except Exception as e:
        print(f"  ✗ Poll error: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# WEBHOOK — GET (Meta verification handshake)
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/webhook")
async def verify_webhook(request: Request):
    """
    Meta calls this GET endpoint to verify the webhook URL.
    Must return the hub.challenge value as plain text.
    """
    params     = dict(request.query_params)
    mode       = params.get("hub.mode")
    token      = params.get("hub.verify_token")
    challenge  = params.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        print(f"✓ Webhook verified by Meta.")
        return PlainTextResponse(content=challenge, status_code=200)

    print(f"✗ Webhook verification failed. Token received: {token}")
    return PlainTextResponse(content="Forbidden", status_code=403)


# ─────────────────────────────────────────────────────────────────────────────
# WEBHOOK — POST (button tap from approver)
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/webhook")
async def receive_webhook(request: Request):
    """
    Meta POSTs here when the approver taps Approve or Reject.
    Payload format: "APPROVE_12345" or "REJECT_12345"
    """
    body = await request.json()

    try:
        entry   = body["entry"][0]["changes"][0]["value"]
        message = entry["messages"][0]

        # Only handle interactive quick-reply button taps
        if message.get("type") != "interactive":
            return {"status": "ignored — not interactive"}

        interactive = message.get("interactive", {})
        if interactive.get("type") != "button_reply":
            return {"status": "ignored — not button_reply"}

        raw_payload = interactive["button_reply"]["id"]
        # e.g. "APPROVE_1042" or "REJECT_1042"

        parts = raw_payload.split("_", 1)
        if len(parts) != 2 or parts[0] not in ("APPROVE", "REJECT"):
            print(f"⚠ Unexpected payload format: {raw_payload}")
            return {"status": "bad payload"}

        action       = parts[0]          # "APPROVE" or "REJECT"
        wdd_code     = int(parts[1])     # e.g. 1042
        sender_phone = message["from"]   # e.g. "919876543210"

        print(f"\n[WEBHOOK] {action} for WddCode={wdd_code} from {sender_phone}")

        # Get doc type before updating (needed for confirmation message)
        wdd_info = get_wdd_status(wdd_code)
        doc_type = map_doc_type(wdd_info["ObjType"]) if wdd_info else "Purchase Order"

        # Apply decision to SAP B1
        result = apply_approval_decision(
            wdd_code=wdd_code,
            action=action,
            remarks=(
                f"{'Approved' if action == 'APPROVE' else 'Rejected'} "
                f"via WhatsApp by {sender_phone} "
                f"at {datetime.now().strftime('%d-%m-%Y %H:%M')}"
            )
        )

        print(f"  SAP result: {result}")

        # Send confirmation back to approver
        send_confirmation_message(
            to_phone=sender_phone,
            wdd_code=wdd_code,
            action=action,
            doc_type=doc_type,
            success=result["success"]
        )

    except KeyError as e:
        print(f"⚠ Webhook parse error — missing key: {e}")
    except Exception as e:
        print(f"✗ Webhook error: {e}")

    # Always return 200 to Meta — otherwise it retries endlessly
    return {"status": "ok"}


# ─────────────────────────────────────────────────────────────────────────────
# TEST — Manual WhatsApp send for debugging
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/test-wa")
async def test_wa():
    """
    Hit /test-wa to send a test template message and see the full API response.
    Helps diagnose token, phone ID, template name, and parameter issues.
    """
    url     = f"https://graph.facebook.com/v19.0/{WA_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WA_TOKEN}",
        "Content-Type":  "application/json"
    }

    # Step 1: Verify token by fetching phone number info
    check_url = f"https://graph.facebook.com/v19.0/{WA_PHONE_ID}"
    check_headers = {"Authorization": f"Bearer {WA_TOKEN}"}
    try:
        check_resp = httpx.get(check_url, headers=check_headers, timeout=10)
        phone_info = check_resp.json()
    except Exception as e:
        phone_info = {"error": str(e)}

    # Step 2: Try sending a test template message
    payload = {
        "messaging_product": "whatsapp",
        "to":   APPROVER_PHONE,
        "type": "template",
        "template": {
            "name":     TEMPLATE_NAME,
            "language": {"code": "en"},
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "parameter_name": "wdd_code",  "text": "99999"},
                        {"type": "text", "parameter_name": "doc_type",  "text": "Purchase Order"},
                        {"type": "text", "parameter_name": "vendor",    "text": "Test Vendor"},
                        {"type": "text", "parameter_name": "amount",    "text": "1,000"},
                        {"type": "text", "parameter_name": "raised_by", "text": "Test User"},
                    ]
                },
                {
                    "type":      "button",
                    "sub_type":  "quick_reply",
                    "index":     "0",
                    "parameters": [{"type": "payload",
                                    "payload": "APPROVE_99999"}]
                },
                {
                    "type":      "button",
                    "sub_type":  "quick_reply",
                    "index":     "1",
                    "parameters": [{"type": "payload",
                                    "payload": "REJECT_99999"}]
                }
            ]
        }
    }

    try:
        resp = httpx.post(url, json=payload, headers=headers, timeout=10)
        send_result = resp.json()
        send_status = resp.status_code
    except Exception as e:
        send_result = {"error": str(e)}
        send_status = 0

    return {
        "phone_number_id":  WA_PHONE_ID,
        "approver_phone":   APPROVER_PHONE,
        "template_name":    TEMPLATE_NAME,
        "phone_info_check": phone_info,
        "send_status_code": send_status,
        "send_response":    send_result,
        "payload_sent":     payload,
    }


# ─────────────────────────────────────────────────────────────────────────────
# HEALTH CHECK
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status":            "running",
        "already_sent_count": len(_already_sent),
        "time":              datetime.now().isoformat(),
        "hana_schema":       HANA_SCHEMA,
        "approver_phone":    APPROVER_PHONE,
        "template":          TEMPLATE_NAME,
    }


# ─────────────────────────────────────────────────────────────────────────────
# STARTUP
# ─────────────────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    print("=" * 60)
    print("  Jivo WA Approval Service starting...")
    print(f"  HANA: {HANA_HOST}:{HANA_PORT} | Schema: {HANA_SCHEMA}")
    print(f"  Template: {TEMPLATE_NAME}")
    print(f"  Approver: {APPROVER_PHONE}")
    print("=" * 60)

    create_tracking_table()
    load_sent_from_hana()

    scheduler = BackgroundScheduler()
    scheduler.add_job(poll_and_send, "interval", seconds=60, id="po_poll")
    scheduler.start()
    print("✓ Scheduler started — polling every 60 seconds.\n")