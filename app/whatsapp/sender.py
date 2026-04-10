from datetime import datetime

import re

import httpx

from app.config import WA_TOKEN, WA_PHONE_ID, APPROVER_PHONES, CONFIRMATION_PHONES, TEMPLATE_NAME, CONFIRM_TMPL, ERROR_TMPL, ITEMS_TMPL
from app.logging_setup import log_wa
from app.whatsapp.constants import map_doc_type

WA_API_URL = f"https://graph.facebook.com/v19.0/{WA_PHONE_ID}/messages"
WA_HEADERS = {
    "Authorization": f"Bearer {WA_TOKEN}",
    "Content-Type": "application/json",
}


def _sanitize_param(text: str) -> str:
    """Sanitize text for WhatsApp template parameters.

    Meta rejects params with newlines, tabs, or more than 4 consecutive spaces.
    """
    text = text.replace("\n", " ").replace("\r", " ").replace("\t", " ")
    text = re.sub(r" {4,}", "   ", text)
    return text.strip()


def _send_items_template(to_phone: str, wdd_code, po_number, items: list[dict]) -> bool:
    """Send one template message per item (works without 24-hour window).

    Each item gets its own message so there is no character limit issue.
    Returns True if all items were sent successfully.
    """
    total = len(items)
    all_ok = True
    for i, item in enumerate(items, 1):
        code = item.get("ItemCode", "")
        name = item.get("ItemName", "N/A")
        demand = item.get("POQuantity") or 0
        instock = item.get("CurrentStock") or 0
        benchmark = item.get("MinimumStock") or 0

        payload = {
            "messaging_product": "whatsapp",
            "to": to_phone,
            "type": "template",
            "template": {
                "name": ITEMS_TMPL,
                "language": {"code": "en"},
                "components": [
                    {
                        "type": "body",
                        "parameters": [
                            {"type": "text", "parameter_name": "code", "text": _sanitize_param(str(code))},
                            {"type": "text", "parameter_name": "name", "text": _sanitize_param(str(name))},
                            {"type": "text", "parameter_name": "demand", "text": f"{demand:,.0f}"},
                            {"type": "text", "parameter_name": "instock", "text": f"{instock:,.0f}"},
                            {"type": "text", "parameter_name": "benchmark", "text": f"{benchmark:,.0f}"},
                        ],
                    }
                ],
            },
        }
        try:
            resp = httpx.post(WA_API_URL, json=payload, headers=WA_HEADERS, timeout=10)
            if resp.status_code == 200:
                log_wa.info("ITEM TMPL SENT WddCode=%s | Item %d/%d | To=%s", wdd_code, i, total, to_phone)
            else:
                all_ok = False
                log_wa.error(
                    "ITEM TMPL FAILED WddCode=%s | Item %d/%d | To=%s | Status=%s | Response=%s",
                    wdd_code, i, total, to_phone, resp.status_code, resp.text,
                )
        except Exception as e:
            all_ok = False
            log_wa.error("ITEM TMPL EXCEPTION WddCode=%s | Item %d/%d | To=%s: %s", wdd_code, i, total, to_phone, e)
    return all_ok


def send_whatsapp_approval(approval: dict) -> bool:
    """Send approval request template message with item details to approver.

    The approval dict must contain an 'items' list with per-line-item details.
    """
    wdd_code = approval["WddCode"]
    bp_name = approval.get("BPName") or "N/A"
    amount = approval.get("TotalAmount") or 0
    doc_type = map_doc_type(approval.get("ObjType", "22"))
    created_by = approval.get("CreatedBy") or "N/A"
    po_number = approval.get("PONumber") or "N/A"
    items = approval.get("items", [])
    item_summary = f"{len(items)} item(s)"

    any_success = False
    for phone in APPROVER_PHONES:
        payload = {
            "messaging_product": "whatsapp",
            "to": phone,
            "type": "template",
            "template": {
                "name": TEMPLATE_NAME,
                "language": {"code": "en"},
                "components": [
                    {
                        "type": "body",
                        "parameters": [
                            {"type": "text", "parameter_name": "wdd_code", "text": _sanitize_param(str(wdd_code))},
                            {"type": "text", "parameter_name": "doc_type", "text": _sanitize_param(doc_type)},
                            {"type": "text", "parameter_name": "vendor", "text": _sanitize_param(bp_name)},
                            {"type": "text", "parameter_name": "po_number", "text": _sanitize_param(str(po_number))},
                            {"type": "text", "parameter_name": "amount", "text": _sanitize_param(f"{amount:,.0f}")},
                            {"type": "text", "parameter_name": "raised_by", "text": _sanitize_param(created_by)},
                            {"type": "text", "parameter_name": "items", "text": _sanitize_param(item_summary)},
                        ],
                    },
                    {
                        "type": "button",
                        "sub_type": "quick_reply",
                        "index": "0",
                        "parameters": [{"type": "payload", "payload": f"APPROVE_{wdd_code}"}],
                    },
                    {
                        "type": "button",
                        "sub_type": "quick_reply",
                        "index": "1",
                        "parameters": [{"type": "payload", "payload": f"REJECT_{wdd_code}"}],
                    },
                ],
            },
        }
        try:
            resp = httpx.post(WA_API_URL, json=payload, headers=WA_HEADERS, timeout=10)
            if resp.status_code == 200:
                any_success = True
                log_wa.info(
                    "WA SENT WddCode=%s | %s | %s | PO=%s | Amount=%s | Items=%d | To=%s",
                    wdd_code, doc_type, bp_name, po_number, f"{amount:,.0f}",
                    len(items), phone,
                )
                if items:
                    if _send_items_template(phone, wdd_code, po_number, items):
                        log_wa.info("ITEMS TMPL SENT WddCode=%s | %d items | To=%s", wdd_code, len(items), phone)
                    else:
                        log_wa.warning("ITEMS TMPL FAILED WddCode=%s | To=%s — approval template was sent OK", wdd_code, phone)
            else:
                log_wa.error(
                    "WA FAILED WddCode=%s | To=%s | Status=%s | Response=%s",
                    wdd_code, phone, resp.status_code, resp.text,
                )
        except Exception as e:
            log_wa.error("WA EXCEPTION WddCode=%s | To=%s: %s", wdd_code, phone, e)
    return any_success


def send_confirmation_message(wdd_code: int, action: str,
                              doc_type: str, success: bool,
                              po_number: str = "N/A", vendor: str = "N/A",
                              amount: str = "0", raised_by: str = "N/A"):
    """Send confirmation template to all CONFIRMATION_PHONES after approval/rejection."""
    if not success:
        log_wa.warning("Skipping confirmation for WddCode=%s — SAP update failed", wdd_code)
        return

    status_text = "APPROVED" if action == "APPROVE" else "REJECTED"
    time_str = datetime.now().strftime("%d %b %Y, %I:%M %p")

    for phone in CONFIRMATION_PHONES:
        payload = {
            "messaging_product": "whatsapp",
            "to": phone,
            "type": "template",
            "template": {
                "name": CONFIRM_TMPL,
                "language": {"code": "en"},
                "components": [
                    {
                        "type": "body",
                        "parameters": [
                            {"type": "text", "parameter_name": "wdd_code", "text": str(wdd_code)},
                            {"type": "text", "parameter_name": "po_number", "text": _sanitize_param(str(po_number))},
                            {"type": "text", "parameter_name": "doc_type", "text": _sanitize_param(doc_type)},
                            {"type": "text", "parameter_name": "vendor", "text": _sanitize_param(vendor)},
                            {"type": "text", "parameter_name": "amount", "text": _sanitize_param(str(amount))},
                            {"type": "text", "parameter_name": "raised_by", "text": _sanitize_param(raised_by)},
                            {"type": "text", "parameter_name": "action", "text": status_text},
                            {"type": "text", "parameter_name": "time", "text": time_str},
                        ],
                    }
                ],
            },
        }
        try:
            resp = httpx.post(WA_API_URL, json=payload, headers=WA_HEADERS, timeout=10)
            if resp.status_code == 200:
                log_wa.info("CONFIRMATION SENT WddCode=%s | %s | To=%s", wdd_code, status_text, phone)
            else:
                log_wa.error(
                    "CONFIRMATION FAILED WddCode=%s | To=%s | Status=%s | Response=%s",
                    wdd_code, phone, resp.status_code, resp.text,
                )
        except Exception as e:
            log_wa.error("CONFIRMATION EXCEPTION WddCode=%s | To=%s: %s", wdd_code, phone, e)


def send_error_message(wdd_code: int, attempted_action: str,
                       current_status: str):
    """Send error template to all CONFIRMATION_PHONES when user tries to act on an already-processed PO.

    Example: user approved a PO, then taps Reject — this sends an error message
    explaining the PO was already processed.
    """
    status_map = {"Y": "APPROVED", "N": "REJECTED"}
    current_status_text = status_map.get(current_status, current_status)
    attempted_text = "APPROVE" if attempted_action == "APPROVE" else "REJECT"
    time_str = datetime.now().strftime("%d %b %Y, %I:%M %p")

    for phone in CONFIRMATION_PHONES:
        payload = {
            "messaging_product": "whatsapp",
            "to": phone,
            "type": "template",
            "template": {
                "name": ERROR_TMPL,
                "language": {"code": "en"},
                "components": [
                    {
                        "type": "body",
                        "parameters": [
                            {"type": "text", "parameter_name": "wdd_code", "text": str(wdd_code)},
                            {"type": "text", "parameter_name": "current_status", "text": current_status_text},
                            {"type": "text", "parameter_name": "attempted_action", "text": attempted_text},
                            {"type": "text", "parameter_name": "time", "text": time_str},
                        ],
                    }
                ],
            },
        }
        try:
            resp = httpx.post(WA_API_URL, json=payload, headers=WA_HEADERS, timeout=10)
            if resp.status_code == 200:
                log_wa.info(
                    "ERROR MSG SENT WddCode=%s | Already %s, tried to %s | To=%s",
                    wdd_code, current_status_text, attempted_text, phone,
                )
            else:
                log_wa.error(
                    "ERROR MSG FAILED WddCode=%s | To=%s | Status=%s | Response=%s",
                    wdd_code, phone, resp.status_code, resp.text,
                )
        except Exception as e:
            log_wa.error("ERROR MSG EXCEPTION WddCode=%s | To=%s: %s", wdd_code, phone, e)
