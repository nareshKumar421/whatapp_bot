from datetime import datetime

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.config import HANA_SCHEMA, APPROVER_PHONES, TEMPLATE_NAME
from app.db.tracking import get_sent_count

router = APIRouter()


@router.get("/health")
async def health():
    from main import scheduler

    scheduler_ok = scheduler is not None and scheduler.running

    data = {
        "status": "running" if scheduler_ok else "degraded",
        "scheduler": "running" if scheduler_ok else "stopped",
        "sent_count": get_sent_count(),
        "time": datetime.now().isoformat(),
        "hana_schema": HANA_SCHEMA,
        "approver_phones": APPROVER_PHONES,
        "template": TEMPLATE_NAME,
    }

    if not scheduler_ok:
        return JSONResponse(data, status_code=503)
    return data
