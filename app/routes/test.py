import httpx
from fastapi import APIRouter

from app.config import WA_TOKEN, WA_PHONE_ID, APPROVER_PHONES, TEMPLATE_NAME, ITEMS_TMPL
from app.logging_setup import log_wa

router = APIRouter()


@router.get("/test-wa")
async def test_wa():
    url = f"https://graph.facebook.com/v19.0/{WA_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WA_TOKEN}",
        "Content-Type": "application/json",
    }

    check_url = f"https://graph.facebook.com/v19.0/{WA_PHONE_ID}"
    check_headers = {"Authorization": f"Bearer {WA_TOKEN}"}
    try:
        check_resp = httpx.get(check_url, headers=check_headers, timeout=10)
        phone_info = check_resp.json()
    except Exception as e:
        phone_info = {"error": str(e)}

    results = []
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
                            {"type": "text", "parameter_name": "wdd_code", "text": "99999"},
                            {"type": "text", "parameter_name": "doc_type", "text": "Purchase Order"},
                            {"type": "text", "parameter_name": "vendor", "text": "Test Vendor"},
                            {"type": "text", "parameter_name": "po_number", "text": "TEST-001"},
                            {"type": "text", "parameter_name": "amount", "text": "1,000"},
                            {"type": "text", "parameter_name": "raised_by", "text": "Test User"},
                            {"type": "text", "parameter_name": "items", "text": "2 item(s)"},
                        ],
                    },
                    {
                        "type": "button",
                        "sub_type": "quick_reply",
                        "index": "0",
                        "parameters": [{"type": "payload", "payload": "APPROVE_99999"}],
                    },
                    {
                        "type": "button",
                        "sub_type": "quick_reply",
                        "index": "1",
                        "parameters": [{"type": "payload", "payload": "REJECT_99999"}],
                    },
                ],
            },
        }
        try:
            resp = httpx.post(url, json=payload, headers=headers, timeout=10)
            results.append({"phone": phone, "status": resp.status_code, "response": resp.json()})
            log_wa.info("TEST WA send to %s: status=%s response=%s", phone, resp.status_code, resp.text)
        except Exception as e:
            results.append({"phone": phone, "status": 0, "response": {"error": str(e)}})
            log_wa.error("TEST WA send error to %s: %s", phone, e)

    return {
        "phone_number_id": WA_PHONE_ID,
        "approver_phones": APPROVER_PHONES,
        "template_name": TEMPLATE_NAME,
        "phone_info_check": phone_info,
        "results": results,
    }


@router.get("/test-items")
async def test_items():
    """Test the item detail template (po_information_v1) with dummy data."""
    url = f"https://graph.facebook.com/v19.0/{WA_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WA_TOKEN}",
        "Content-Type": "application/json",
    }

    results = []
    phone = APPROVER_PHONES[0]
    payload = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "template",
        "template": {
            "name": ITEMS_TMPL,
            "language": {"code": "en"},
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "parameter_name": "code", "text": "ITM-001"},
                        {"type": "text", "parameter_name": "name", "text": "Test Item"},
                        {"type": "text", "parameter_name": "demand", "text": "500"},
                        {"type": "text", "parameter_name": "instock", "text": "200"},
                        {"type": "text", "parameter_name": "benchmark", "text": "100"},
                    ],
                }
            ],
        },
    }
    try:
        resp = httpx.post(url, json=payload, headers=headers, timeout=10)
        results.append({"phone": phone, "status": resp.status_code, "response": resp.json()})
        log_wa.info("TEST ITEMS send to %s: status=%s response=%s", phone, resp.status_code, resp.text)
    except Exception as e:
        results.append({"phone": phone, "status": 0, "response": {"error": str(e)}})
        log_wa.error("TEST ITEMS send error to %s: %s", phone, e)

    return {
        "template_name": ITEMS_TMPL,
        "phone": phone,
        "results": results,
    }
