"""In-memory ring buffer of recent log records — for the mini-app Admin Console.

A ``logging.Handler`` keeps the last ~250 formatted records (INFO+) in a deque so
the owner can read recent logs / errors from the phone (``/api/miniapp/admin/logs``)
WITHOUT shell access to the Coolify/stdout stream. Secrets (DSN passwords, the bot
token) are redacted before a record is stored, so a leaked log line can't leak a
credential.

Install once at startup (``create_app`` calls ``install_log_buffer``); idempotent.
"""
import logging
import re
from collections import deque

# General ring (all INFO+). Bumped 250→1500: at ~1KB/record that's ~1.5MB, trivial
# on a 24GB VPS, and the old 250 was evicted in minutes by the routine cultivation_tick
# WARNING + monitor INFO flood — so a real error was gone before the owner could read it.
_MAX_RECORDS = 1500
_buffer: deque = deque(maxlen=_MAX_RECORDS)

# DEDICATED error ring (ERROR+ only). The routine INFO/WARNING flood CANNOT evict it,
# so the panel's "ERR" filter shows real error history (not just whatever survived the
# last few minutes). This is the fix for "the panel doesn't work like Coolify".
_ERR_MAX = 200
_error_buffer: deque = deque(maxlen=_ERR_MAX)

_LEVELS = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}

# Redact `://user:password@` → `://user:***@` and bot-token-shaped strings.
_DSN_RE = re.compile(r"(://[^:/@\s]+:)[^@\s]*(@)")
_TOKEN_RE = re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{30,}\b")


def _redact(s: str) -> str:
    s = _DSN_RE.sub(r"\1***\2", s)
    s = _TOKEN_RE.sub("***", s)
    return s


class RingBufferHandler(logging.Handler):
    """Stores each emitted record (redacted) into the module-level ring buffer."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)  # default Formatter appends exc traceback
            rec = {
                "ts": int(record.created * 1000),
                "level": record.levelname,
                "logger": record.name,
                "msg": _redact(msg)[:4000],  # 4000 so a full traceback isn't clipped
            }
            _buffer.append(rec)
            if record.levelno >= logging.ERROR:
                _error_buffer.append(rec)  # survives the routine INFO/WARNING flood
        except Exception:
            pass  # logging must never raise


_installed = False


def install_log_buffer(level: int = logging.INFO) -> None:
    """Attach the ring-buffer handler to the root logger (idempotent)."""
    global _installed
    if _installed:
        return
    handler = RingBufferHandler(level=level)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logging.getLogger().addHandler(handler)
    _installed = True


def get_recent_logs(level: str | None = None, contains: str | None = None,
                    limit: int = 100) -> list[dict]:
    """Return up to ``limit`` most-recent buffered records, newest LAST, optionally
    filtered by minimum ``level`` and a ``contains`` substring (msg or logger).

    When the caller asks specifically for ERROR/CRITICAL, serve from the dedicated
    error ring so errors are never hidden by the routine INFO/WARNING flood (the
    panel's "ERR" tab = real error history)."""
    src = _error_buffer if (level and level.upper() in ("ERROR", "CRITICAL")) else _buffer
    items = list(src)
    if level and level.upper() in _LEVELS:
        minlv = _LEVELS[level.upper()]
        items = [r for r in items if _LEVELS.get(r["level"], 0) >= minlv]
    if contains:
        c = contains.lower()
        items = [r for r in items if c in r["msg"].lower() or c in r["logger"].lower()]
    if limit and limit > 0:
        items = items[-limit:]
    return items
