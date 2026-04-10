import os
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.config import (
    HANA_HOST, HANA_PORT, HANA_SCHEMA,
    APPROVER_PHONES, CONFIRMATION_PHONES, TEMPLATE_NAME, CONFIRM_TMPL, ERROR_TMPL, ITEMS_TMPL, WA_PHONE_ID,
)
from app.db.queries import get_pending_approvals
from app.db.tracking import get_sent_records
from app.logging_setup import LOG_DIR
from app.stats import get_stats_snapshot

router = APIRouter()

TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "templates")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

LOG_FILES = ["app.log", "error.log", "webhook.log", "whatsapp.log", "poll.log", "hana.log"]


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Full dashboard showing all app stats, logs, and JIVO_WA_SENT records."""
    now = datetime.now()
    stats = get_stats_snapshot()

    # Uptime
    uptime = ""
    if stats["start_time"]:
        delta = now - datetime.strptime(stats["start_time"], "%Y-%m-%d %H:%M:%S")
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        days, hours = divmod(hours, 24)
        uptime = f"{days}d {hours}h {minutes}m" if days > 0 else f"{hours}h {minutes}m {seconds}s"

    # Pending POs from view
    try:
        pending_approvals = get_pending_approvals()
    except Exception:
        pending_approvals = []

    # Sent records from HANA
    sent_records = get_sent_records()
    for rec in sent_records:
        for ts_field in ("SentAt", "ActionAt"):
            val = rec.get(ts_field, "")
            if hasattr(val, "strftime"):
                rec[ts_field] = val.strftime("%Y-%m-%d %H:%M:%S")
            elif not val:
                rec[ts_field] = ""

    # Computed metrics
    approved_count = sum(1 for r in sent_records if r.get("Status") == "APPROVE")
    rejected_count = sum(1 for r in sent_records if r.get("Status") == "REJECT")
    pending_count = len(sent_records) - approved_count - rejected_count

    total_decisions = stats["approvals"] + stats["rejections"]
    approval_rate = round(stats["approvals"] / total_decisions * 100) if total_decisions > 0 else 0
    rejection_rate = round(stats["rejections"] / total_decisions * 100) if total_decisions > 0 else 0

    total_attempts = stats["messages_sent"] + stats["messages_failed"]
    send_success_rate = round(stats["messages_sent"] / total_attempts * 100) if total_attempts > 0 else 100

    # Read last 100 lines from each log file
    log_data: dict[str, str] = {}
    for lf in LOG_FILES:
        path = os.path.join(LOG_DIR, lf)
        try:
            with open(path, "r") as f:
                all_lines = f.readlines()
                log_data[lf] = "".join(all_lines[-100:])
        except FileNotFoundError:
            log_data[lf] = "(empty)"

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "uptime": uptime or "Starting...",
        "stats": stats,
        "sent_records": sent_records,
        "log_files": LOG_FILES,
        "log_data": log_data,
        "approved_count": approved_count,
        "rejected_count": rejected_count,
        "pending_count": pending_count,
        "approval_rate": approval_rate,
        "rejection_rate": rejection_rate,
        "send_success_rate": send_success_rate,
        "pending_approvals": pending_approvals,
        "config": {
            "hana_host": f"{HANA_HOST}:{HANA_PORT}",
            "schema": HANA_SCHEMA,
            "approver_phones": ", ".join(APPROVER_PHONES),
            "confirmation_phones": ", ".join(CONFIRMATION_PHONES),
            "template": TEMPLATE_NAME,
            "confirm_template": CONFIRM_TMPL,
            "error_template": ERROR_TMPL,
            "items_template": ITEMS_TMPL,
            "wa_phone_id": WA_PHONE_ID,
        },
        "now": now.strftime("%Y-%m-%d %H:%M:%S"),
    })
