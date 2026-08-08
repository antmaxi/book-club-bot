from __future__ import annotations

import asyncio
import logging
import logging.handlers
import os
from collections import deque

from telegram.ext import Application

from bookclub.config import ERROR_ALERTS, INSTANCE_NAME, LOG_FILE
import bookclub.config as config

_log_fmt = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

_console_handler = logging.StreamHandler()
_console_handler.setFormatter(_log_fmt)

_handlers: list[logging.Handler] = [_console_handler]

# The log directory is not in git (see .gitignore), so on a fresh clone it does
# not exist yet and RotatingFileHandler would raise at import time — taking the
# whole module, and the test suite, down with it.
_log_dir = os.path.dirname(LOG_FILE)
try:
    if _log_dir:
        os.makedirs(_log_dir, exist_ok=True)
    _file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    _file_handler.setFormatter(_log_fmt)
    _handlers.append(_file_handler)
except OSError as e:
    # Read-only filesystem, bad LOG_FILE path, … — console logging still works.
    print(f"Warning: file logging disabled ({LOG_FILE}): {e}")

logging.basicConfig(level=logging.INFO, handlers=_handlers)
logger = logging.getLogger(__name__)

# ── Error alerting to Telegram ───────────────────────────────────────────────────
# Anything logged at ERROR or above is forwarded to the main admin's Telegram
# chat, so failures surface immediately instead of sitting unread in the log
# file. The logging handler runs synchronously (and may fire before the event
# loop even exists, e.g. during import), so it only *buffers* records; a
# background task started at startup drains the buffer and does the sending.
ERROR_ALERTS = os.environ.get("ERROR_ALERTS", "1").lower() not in (
    "0",
    "false",
    "no",
    "",
)
# Optional label so a shared admin can tell which bot an alert came from.
INSTANCE_NAME = os.environ.get("INSTANCE_NAME", "")

# Bounded so a burst of errors — or a wedged loop that never drains this —
# can't grow memory without limit; oldest alerts are dropped first.
_ALERT_BUFFER_MAX = 200
_alert_buffer: deque[str] = deque(maxlen=_ALERT_BUFFER_MAX)
_alert_dropped = 0  # records discarded because the buffer was full

_ALERT_FLUSH_INTERVAL = 3.0  # seconds between sends — a basic rate limit
_ALERT_MAX_PER_FLUSH = 5  # records coalesced into one message per flush

# Loggers whose failures we must NOT alert on, or we risk a feedback loop:
# sending an alert can itself fail deep inside httpx/telegram and log an error,
# which would enqueue another alert, which fails again, forever.
_ALERT_SKIP_PREFIXES = ("httpx", "httpcore", "telegram", "apscheduler")


class _TelegramAlertHandler(logging.Handler):
    """Buffer ERROR+ log records for later delivery to the admin via Telegram."""

    def emit(self, record: logging.LogRecord) -> None:
        global _alert_dropped
        name = record.name or ""
        # ".alert" is our own delivery-failure logger (see _alert_logger); the
        # prefixes are the networking stack that a failing send screams from.
        if name.endswith(".alert") or name.startswith(_ALERT_SKIP_PREFIXES):
            return
        try:
            msg = self.format(record)
        except Exception:
            return
        if len(_alert_buffer) == _alert_buffer.maxlen:
            _alert_dropped += 1
        _alert_buffer.append(msg)


# Child logger for reporting alert-delivery failures. Its name ends in
# ".alert" so _TelegramAlertHandler.emit() skips it — otherwise a failed send
# would try to alert about itself and never stop.
_alert_logger = logger.getChild("alert")

if ERROR_ALERTS:
    _alert_handler = _TelegramAlertHandler(level=logging.ERROR)
    _alert_handler.setFormatter(_log_fmt)
    logging.getLogger().addHandler(_alert_handler)


async def _drain_alert_queue(app: Application) -> None:
    """Forward buffered ERROR logs to the main admin.

    Runs for the lifetime of the bot. Coalesces up to _ALERT_MAX_PER_FLUSH
    records into a single message every _ALERT_FLUSH_INTERVAL seconds, so a
    storm of errors can't turn into a storm of notifications.
    """
    global _alert_dropped
    admin_id = config.ADMIN_IDS[0]
    prefix = f"[{INSTANCE_NAME}] " if INSTANCE_NAME else ""
    while True:
        await asyncio.sleep(_ALERT_FLUSH_INTERVAL)
        if not _alert_buffer:
            continue

        batch: list[str] = []
        while _alert_buffer and len(batch) < _ALERT_MAX_PER_FLUSH:
            batch.append(_alert_buffer.popleft())
        dropped, _alert_dropped = _alert_dropped, 0

        header = f"{prefix}⚠️ {len(batch)} error(s) logged"
        if dropped:
            header += f" (+{dropped} dropped)"
        if _alert_buffer:
            header += f" (+{len(_alert_buffer)} still queued)"
        text = f"{header}:\n\n" + "\n\n".join(batch)
        if len(text) > 3900:  # Telegram caps messages at 4096; leave headroom
            text = text[:3900] + "\n… (truncated)"

        try:
            # Plain text on purpose: tracebacks are full of Markdown-special
            # characters that would break parse_mode rendering (or get dropped).
            await app.bot.send_message(chat_id=admin_id, text=text)
        except Exception as e:
            # Reported via the ".alert" child so this failure is not itself
            # turned into an alert (which could not be delivered either).
            _alert_logger.warning(f"Could not deliver error alert: {e}")

