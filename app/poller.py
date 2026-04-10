from datetime import datetime

from app.db.queries import get_pending_approvals
from app.db.tracking import try_mark_as_sent
from app.logging_setup import log_poll
from app.stats import increment_stat, set_stat, add_activity
from app.whatsapp.constants import map_doc_type
from app.whatsapp.sender import send_whatsapp_approval


def poll_and_send():
    """Fetch pending PO approvals from HANA and send WhatsApp messages."""
    increment_stat("polls")
    set_stat("last_poll", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    log_poll.info("Polling HANA for pending approvals...")

    try:
        approvals = get_pending_approvals()
        log_poll.info("Found %d pending approvals", len(approvals))

        for approval in approvals:
            wdd_code = approval["WddCode"]

            # Atomic insert — returns False if already sent (no race condition)
            if not try_mark_as_sent(wdd_code):
                continue

            bp = approval.get("BPName") or "N/A"
            amount = approval.get("TotalAmount") or 0
            po_number = approval.get("PONumber") or "N/A"
            doc_type = map_doc_type(approval.get("ObjType", "22"))
            item_count = len(approval.get("items", []))

            log_poll.info(
                "Sending WddCode=%s | %s | %s | PO=%s | Amount=%s | Items=%d",
                wdd_code, doc_type, bp, po_number, f"{amount:,.0f}", item_count,
            )
            sent = send_whatsapp_approval(approval)

            if sent:
                increment_stat("messages_sent")
                set_stat("last_message_sent", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                add_activity("SENT", f"WddCode={wdd_code} | {doc_type} | {bp} | PO={po_number} | {amount:,.0f} | {item_count} items")
            else:
                increment_stat("messages_failed")
                add_activity("FAILED", f"WddCode={wdd_code} — will retry next poll")
                log_poll.warning("Will retry WddCode=%s on next poll", wdd_code)

    except Exception as e:
        log_poll.error("Poll error: %s", e)
        increment_stat("hana_errors")
        add_activity("ERROR", f"Poll error: {e}")
