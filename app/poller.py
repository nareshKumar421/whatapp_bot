from datetime import datetime

from app.db.queries import get_pending_approvals
from app.db.tracking import is_already_sent, mark_as_sent
from app.logging_setup import log_poll
from app.stats import stats, add_activity
from app.whatsapp.constants import map_doc_type
from app.whatsapp.sender import send_whatsapp_approval


def poll_and_send():
    """Fetch pending PO approvals from HANA and send WhatsApp messages."""
    stats["polls"] += 1
    stats["last_poll"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_poll.info("Polling HANA for pending approvals...")

    try:
        approvals = get_pending_approvals()
        new_ones = [a for a in approvals if not is_already_sent(a["WddCode"])]
        log_poll.info("Found %d pending | %d new to send", len(approvals), len(new_ones))

        for approval in new_ones:
            wdd_code = approval["WddCode"]
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
                mark_as_sent(wdd_code)
                stats["messages_sent"] += 1
                stats["last_message_sent"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                add_activity("SENT", f"WddCode={wdd_code} | {doc_type} | {bp} | PO={po_number} | {amount:,.0f} | {item_count} items")
            else:
                stats["messages_failed"] += 1
                add_activity("FAILED", f"WddCode={wdd_code} — will retry next poll")
                log_poll.warning("Will retry WddCode=%s on next poll", wdd_code)

    except Exception as e:
        log_poll.error("Poll error: %s", e)
        stats["hana_errors"] += 1
        add_activity("ERROR", f"Poll error: {e}")
