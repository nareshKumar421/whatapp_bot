import json
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

from app.config import VERIFY_TOKEN
from app.db.queries import get_wdd_status, get_po_details, apply_approval_decision
from app.logging_setup import log_webhook
from app.stats import increment_stat, set_stat, add_activity
from app.whatsapp.constants import map_doc_type
from app.whatsapp.sender import send_confirmation_message, send_error_message

router = APIRouter()


@router.get("/webhook")
async def verify_webhook(request: Request):
    params = dict(request.query_params)
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        log_webhook.info("Webhook verified by Meta")
        return PlainTextResponse(content=challenge, status_code=200)

    log_webhook.warning("Webhook verification failed. Token received: %s", token)
    return PlainTextResponse(content="Forbidden", status_code=403)


@router.post("/webhook")
async def receive_webhook(request: Request):
    body = await request.json()
    increment_stat("webhook_received")
    set_stat("last_webhook", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    log_webhook.debug("Webhook payload: %s", json.dumps(body, default=str))

    try:
        entry_value = body["entry"][0]["changes"][0]["value"]

        if "messages" not in entry_value:
            field = body["entry"][0]["changes"][0].get("field", "unknown")
            log_webhook.info("Non-message webhook ignored (field=%s)", field)
            return {"status": "ignored — no messages"}

        message = entry_value["messages"][0]
        msg_type = message.get("type")
        raw_payload = None

        if msg_type == "button":
            raw_payload = message.get("button", {}).get("payload")
        elif msg_type == "interactive":
            interactive = message.get("interactive", {})
            if interactive.get("type") == "button_reply":
                raw_payload = interactive["button_reply"].get("id")
            else:
                log_webhook.info("Ignored interactive type: %s", interactive.get("type"))
                return {"status": "ignored — not button_reply"}
        else:
            log_webhook.info("Ignored message type: %s", msg_type)
            return {"status": f"ignored — type {msg_type}"}

        if not raw_payload:
            log_webhook.warning("No payload found in message")
            return {"status": "no payload"}

        parts = raw_payload.split("_", 1)
        if len(parts) != 2 or parts[0] not in ("APPROVE", "REJECT"):
            log_webhook.warning("Unexpected payload format: %s", raw_payload)
            return {"status": "bad payload"}

        action = parts[0]
        try:
            wdd_code = int(parts[1])
        except ValueError:
            log_webhook.warning("Invalid WddCode format: %s", parts[1])
            return {"status": "invalid wdd_code"}

        sender_phone = message["from"]

        log_webhook.info("ACTION=%s | WddCode=%s | From=%s", action, wdd_code, sender_phone)

        wdd_info = get_wdd_status(wdd_code)
        doc_type = map_doc_type(wdd_info["ObjType"]) if wdd_info else "Purchase Order"
        po_details = get_po_details(wdd_code) or {}

        # Check if PO is already processed — send error template instead
        if wdd_info and wdd_info["ProcesStat"] != "W":
            log_webhook.warning(
                "WddCode=%s already processed (status=%s), user tried to %s",
                wdd_code, wdd_info["ProcesStat"], action,
            )
            send_error_message(
                wdd_code=wdd_code,
                attempted_action=action,
                current_status=wdd_info["ProcesStat"],
            )
            add_activity(
                "ERROR",
                f"WddCode={wdd_code} already processed — {action} rejected | by {sender_phone}",
            )
            return {"status": "already_processed"}

        result = apply_approval_decision(
            wdd_code=wdd_code,
            action=action,
            remarks=(
                f"{'Approved' if action == 'APPROVE' else 'Rejected'} "
                f"via WhatsApp by {sender_phone} "
                f"at {datetime.now().strftime('%d-%m-%Y %H:%M')}"
            ),
            source="WhatsApp",
            approved_by=sender_phone,
        )

        log_webhook.info("SAP result for WddCode=%s: %s", wdd_code, result)

        send_confirmation_message(
            wdd_code=wdd_code,
            action=action,
            doc_type=doc_type,
            success=result["success"],
            po_number=str(po_details.get("PONumber", "N/A")),
            vendor=po_details.get("BPName", "N/A"),
            amount=f"{po_details.get('TotalAmount', 0):,.0f}",
            raised_by=po_details.get("CreatedBy", "N/A"),
        )

        if result["success"]:
            if action == "APPROVE":
                increment_stat("approvals")
            else:
                increment_stat("rejections")
            add_activity(action, f"WddCode={wdd_code} | {doc_type} | by {sender_phone}")
        else:
            add_activity("ERROR", f"WddCode={wdd_code} {action} failed: {result['message']}")

    except KeyError as e:
        log_webhook.error("Webhook parse error — missing key: %s", e)
        increment_stat("webhook_errors")
        add_activity("ERROR", f"Webhook parse error: missing key {e}")
    except Exception as e:
        log_webhook.error("Webhook error: %s", e, exc_info=True)
        increment_stat("webhook_errors")
        add_activity("ERROR", f"Webhook error: {e}")

    return {"status": "ok"}
