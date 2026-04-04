import os
import logging
from logging.handlers import RotatingFileHandler

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

_fmt = logging.Formatter(
    "%(asctime)s | %(levelname)-8s | %(name)-18s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def _rotating(filename: str, level: int = logging.DEBUG) -> RotatingFileHandler:
    handler = RotatingFileHandler(
        os.path.join(LOG_DIR, filename), maxBytes=5 * 1024 * 1024, backupCount=10
    )
    handler.setFormatter(_fmt)
    handler.setLevel(level)
    return handler


# File handlers
app_handler = _rotating("app.log")
err_handler = _rotating("error.log", logging.WARNING)
webhook_handler = _rotating("webhook.log")
wa_handler = _rotating("whatsapp.log")
poll_handler = _rotating("poll.log")
hana_handler = _rotating("hana.log")

# Console handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(_fmt)
console_handler.setLevel(logging.INFO)

_common = [app_handler, err_handler, console_handler]


def _make_logger(name: str, extra_handler: RotatingFileHandler | None = None) -> logging.Logger:
    log = logging.getLogger(name)
    log.setLevel(logging.DEBUG)
    for h in _common:
        log.addHandler(h)
    if extra_handler:
        log.addHandler(extra_handler)
    return log


logger = _make_logger("app")
log_webhook = _make_logger("webhook", webhook_handler)
log_wa = _make_logger("whatsapp", wa_handler)
log_poll = _make_logger("poll", poll_handler)
log_hana = _make_logger("hana", hana_handler)
