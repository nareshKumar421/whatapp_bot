from datetime import datetime

from fastapi import APIRouter

from app.config import HANA_SCHEMA, APPROVER_PHONES, TEMPLATE_NAME
from app.db.tracking import get_sent_count

router = APIRouter()


@router.get("/health")
async def health():
    return {
        "status": "running",
        "sent_count": get_sent_count(),
        "time": datetime.now().isoformat(),
        "hana_schema": HANA_SCHEMA,
        "approver_phones": APPROVER_PHONES,
        "template": TEMPLATE_NAME,
    }
