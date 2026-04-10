# ─────────────────────────────────────────────────────────────────────────────
# Jivo Wellness — WhatsApp SAP B1 PO Approval Service
# FastAPI + APScheduler + SAP HANA (hdbcli) + Meta Cloud API
#
# Flow:
#   1. Poll HANA every 10s for OWDD rows with ProcesStat='W', ObjType='22'
#   2. Send WhatsApp template message with Approve / Reject quick-reply buttons
#   3. Receive button tap via Meta webhook POST /webhook
#   4. Update OWDD, WDD1, ODRF in SAP HANA
#   5. Send confirmation message back to approver
# ─────────────────────────────────────────────────────────────────────────────

from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from app.config import HANA_HOST, HANA_PORT, HANA_SCHEMA, TEMPLATE_NAME, APPROVER_PHONES, CONFIRMATION_PHONES, POLL_INTERVAL_SECONDS
import app.metrics  # noqa: F401 — register Prometheus metrics on import
from app.db.tracking import create_tracking_table
from app.logging_setup import logger
from app.poller import poll_and_send
from app.routes import api, dashboard, health, test, webhook
from app.stats import set_stat

app = FastAPI(title="Jivo WA Approval", version="2.0.0")


scheduler = None

# Register routes
app.include_router(webhook.router)
app.include_router(health.router)
app.include_router(test.router)
app.include_router(dashboard.router)
app.include_router(api.router)


@app.get("/metrics")
async def metrics():
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.on_event("startup")
async def startup():
    set_stat("start_time", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    logger.info("=" * 60)
    logger.info("  Jivo WA Approval Service starting...")
    logger.info("  HANA: %s:%s | Schema: %s", HANA_HOST, HANA_PORT, HANA_SCHEMA)
    logger.info("  Template: %s", TEMPLATE_NAME)
    logger.info("  Approvers: %s", ", ".join(APPROVER_PHONES))
    logger.info("  Confirmation: %s", ", ".join(CONFIRMATION_PHONES))
    logger.info("  Poll interval: %ds", POLL_INTERVAL_SECONDS)
    logger.info("=" * 60)

    create_tracking_table()

    global scheduler
    scheduler = BackgroundScheduler()
    scheduler.add_job(poll_and_send, "interval", seconds=POLL_INTERVAL_SECONDS, id="po_poll")
    scheduler.start()
    logger.info("Scheduler started — polling every %d seconds.", POLL_INTERVAL_SECONDS)


@app.on_event("shutdown")
async def shutdown():
    global scheduler
    if scheduler:
        scheduler.shutdown(wait=True)
        logger.info("Scheduler stopped gracefully.")
