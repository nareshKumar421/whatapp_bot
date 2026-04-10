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

from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI

from app.config import HANA_HOST, HANA_PORT, HANA_SCHEMA, TEMPLATE_NAME, APPROVER_PHONES, CONFIRMATION_PHONES
from app.db.tracking import create_tracking_table
from app.logging_setup import logger
from app.poller import poll_and_send
from app.routes import api, dashboard, health, test, webhook
from app.stats import stats

app = FastAPI(title="Jivo WA Approval", version="2.0.0")
scheduler = None

# Register routes
app.include_router(webhook.router)
app.include_router(health.router)
app.include_router(test.router)
app.include_router(dashboard.router)
app.include_router(api.router)


@app.on_event("startup")
async def startup():                                             
    stats["start_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    logger.info("=" * 60)
    logger.info("  Jivo WA Approval Service starting...")
    logger.info("  HANA: %s:%s | Schema: %s", HANA_HOST, HANA_PORT, HANA_SCHEMA)
    logger.info("  Template: %s", TEMPLATE_NAME)
    logger.info("  Approvers: %s", ", ".join(APPROVER_PHONES))
    logger.info("  Confirmation: %s", ", ".join(CONFIRMATION_PHONES))
    logger.info("=" * 60)

    create_tracking_table()

    global scheduler
    scheduler = BackgroundScheduler()
    scheduler.add_job(poll_and_send, "interval", seconds=10, id="po_poll")
    scheduler.start()
    logger.info("Scheduler started — polling every 10 seconds.")
