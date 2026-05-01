from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.db.queries import get_pending_approvals, get_wdd_status, get_po_details, apply_approval_decision
from app.logging_setup import logger
from app.stats import increment_stat, add_activity
from app.whatsapp.constants import map_doc_type
from app.whatsapp.sender import send_confirmation_message

router = APIRouter(prefix="/api")


@router.get("/pending")
async def api_pending():
    """Return pending POs for dashboard display."""
    try:
        approvals = get_pending_approvals()
        return {"status": "ok", "data": approvals}
    except Exception as e:
        logger.error("Error fetching pending approvals: %s", e, exc_info=True)
        return JSONResponse({"status": "error", "message": "Internal server error"}, status_code=500)


@router.post("/decide")
async def api_decide(request: Request):
    """Approve or reject a PO from the dashboard.

    Expects JSON: {"wdd_code": 123, "action": "APPROVE"|"REJECT", "user": "Admin"}
    """
    body = await request.json()
    wdd_code = body.get("wdd_code")
    action = body.get("action", "").upper()
    user = body.get("user", "Dashboard User")

    if not wdd_code or action not in ("APPROVE", "REJECT"):
        return JSONResponse(
            {"success": False, "message": "wdd_code and action (APPROVE/REJECT) are required."},
            status_code=400,
        )

    try:
        wdd_code = int(wdd_code)
    except (ValueError, TypeError):
        return JSONResponse(
            {"success": False, "message": "wdd_code must be a valid integer."},
            status_code=400,
        )

    # Check current status
    wdd_info = get_wdd_status(wdd_code)
    if not wdd_info:
        return JSONResponse(
            {"success": False, "message": f"WddCode {wdd_code} not found."},
            status_code=404,
        )

    if wdd_info["ProcesStat"] != "W":
        status_map = {"Y": "APPROVED", "N": "REJECTED"}
        return JSONResponse(
            {"success": False, "message": f"Already {status_map.get(wdd_info['ProcesStat'], wdd_info['ProcesStat'])}."},
            status_code=409,
        )

    doc_type = map_doc_type(wdd_info["ObjType"])
    po_details = get_po_details(wdd_code) or {}

    result = apply_approval_decision(
        wdd_code=wdd_code,
        action=action,
        remarks=(
            f"{'Approved' if action == 'APPROVE' else 'Rejected'} "
            f"via Dashboard by {user} "
            f"at {datetime.now().strftime('%d-%m-%Y %H:%M')}"
        ),
        source="Dashboard",
        approved_by=user,
    )

    if result["success"]:
        if action == "APPROVE":
            increment_stat("approvals")
        else:
            increment_stat("rejections")
        add_activity(action, f"WddCode={wdd_code} | {doc_type} | via Dashboard by {user}")

        # Send WhatsApp notification to confirmation phones
        send_confirmation_message(
            wdd_code=wdd_code,
            action=action,
            doc_type=doc_type,
            success=True,
            po_number=str(po_details.get("PONumber", "N/A")),
            vendor=po_details.get("BPName", "N/A"),
            amount=f"{po_details.get('TotalAmount', 0):,.0f}",
            raised_by=po_details.get("CreatedBy", "N/A"),
        )
        logger.info("Dashboard %s: WddCode=%s by %s — WA notification sent", action, wdd_code, user)
    else:
        add_activity("ERROR", f"WddCode={wdd_code} Dashboard {action} failed: {result['message']}")

    return result
