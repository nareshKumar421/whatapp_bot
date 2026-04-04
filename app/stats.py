from datetime import datetime

MAX_RECENT = 50

stats = {
    "start_time": None,
    "polls": 0,
    "messages_sent": 0,
    "messages_failed": 0,
    "approvals": 0,
    "rejections": 0,
    "webhook_received": 0,
    "webhook_errors": 0,
    "hana_errors": 0,
    "last_poll": None,
    "last_message_sent": None,
    "last_webhook": None,
    "recent_activity": [],
}


def add_activity(event_type: str, detail: str):
    """Add an event to the recent activity feed."""
    stats["recent_activity"].insert(0, {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "type": event_type,
        "detail": detail,
    })
    if len(stats["recent_activity"]) > MAX_RECENT:
        stats["recent_activity"] = stats["recent_activity"][:MAX_RECENT]
