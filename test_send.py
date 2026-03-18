# Run this after template is approved to send one test WhatsApp message.
# python test_send.py

import os, httpx
from dotenv import load_dotenv
load_dotenv()

WA_TOKEN   = os.getenv("WA_ACCESS_TOKEN")
WA_PHONE_ID = os.getenv("WA_PHONE_NUMBER_ID")
TO_PHONE   = os.getenv("APPROVER_PHONE")
TEMPLATE   = os.getenv("WA_TEMPLATE_NAME", "po_approval_request")

TEST_WDD_CODE = "9999"  # Fake code just for testing

resp = httpx.post(
    f"https://graph.facebook.com/v19.0/{WA_PHONE_ID}/messages",
    headers={
        "Authorization": f"Bearer {WA_TOKEN}",
        "Content-Type":  "application/json"
    },
    json={
        "messaging_product": "whatsapp",
        "to":   TO_PHONE,
        "type": "template",
        "template": {
            "name":     TEMPLATE,
            "language": {"code": "en"},
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "parameter_name": "wdd_code",  "text": TEST_WDD_CODE},
                        {"type": "text", "parameter_name": "doc_type",  "text": "Purchase Order"},
                        {"type": "text", "parameter_name": "vendor",    "text": "Test Vendor Ltd"},
                        {"type": "text", "parameter_name": "amount",    "text": "50,000"},
                        {"type": "text", "parameter_name": "raised_by", "text": "manager"},
                    ]
                },
                {
                    "type": "button", "sub_type": "quick_reply", "index": "0",
                    "parameters": [{"type": "payload",
                                    "payload": f"APPROVE_{TEST_WDD_CODE}"}]
                },
                {
                    "type": "button", "sub_type": "quick_reply", "index": "1",
                    "parameters": [{"type": "payload",
                                    "payload": f"REJECT_{TEST_WDD_CODE}"}]
                }
            ]
        }
    },
    timeout=10
)

print(f"Status : {resp.status_code}")
print(f"Response: {resp.json()}")

if resp.status_code == 200:
    print("\n✓ Message sent! Check your WhatsApp.")
else:
    print("\n✗ Failed. Check your token and phone number in .env")