import os

from dotenv import load_dotenv

load_dotenv()

# SAP HANA
HANA_HOST = os.getenv("HANA_HOST")
HANA_PORT = int(os.getenv("HANA_PORT", 30015))
HANA_USER = os.getenv("HANA_USER")
HANA_PASS = os.getenv("HANA_PASS")
HANA_SCHEMA = os.getenv("HANA_SCHEMA")

# WhatsApp / Meta Cloud API
WA_TOKEN = os.getenv("WA_ACCESS_TOKEN")
WA_PHONE_ID = os.getenv("WA_PHONE_NUMBER_ID")
_approver_raw = os.getenv("APPROVER_PHONE", "")
APPROVER_PHONES = [p.strip() for p in _approver_raw.split(",") if p.strip()]
_confirmation_raw = os.getenv("CONFIRMATION_PHONE", "")
CONFIRMATION_PHONES = [p.strip() for p in _confirmation_raw.split(",") if p.strip()]
TEMPLATE_NAME = os.getenv("WA_TEMPLATE_NAME", "po_approval_request")
CONFIRM_TMPL = os.getenv("WA_CONFIRM_TEMPLATE", "new_template")
ERROR_TMPL = os.getenv("WA_ERROR_TEMPLATE", "po_already_processed_v1")
ITEMS_TMPL = os.getenv("WA_ITEMS_TEMPLATE", "po_item_details")
VERIFY_TOKEN = os.getenv("WA_VERIFY_TOKEN", "jivo_secure_123")
