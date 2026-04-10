import threading
from collections import deque
from datetime import datetime

MAX_RECENT = 50
_lock = threading.Lock()

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
    "recent_activity": deque(maxlen=MAX_RECENT),
}


def increment_stat(key: str, amount: int = 1):
    """Thread-safe increment of a stats counter."""
    with _lock:
        stats[key] += amount


def set_stat(key: str, value):
    """Thread-safe set of a stats value."""
    with _lock:
        stats[key] = value


def add_activity(event_type: str, detail: str):
    """Add an event to the recent activity feed (thread-safe, auto-trimmed)."""
    with _lock:
        stats["recent_activity"].appendleft({
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "type": event_type,
            "detail": detail,
        })


def get_stats_snapshot() -> dict:
    """Return a shallow copy of stats for safe reading."""
    with _lock:
        snapshot = dict(stats)
        snapshot["recent_activity"] = list(stats["recent_activity"])
        return snapshot
