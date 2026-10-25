"""
Debug / Resource Monitor for Nivrael Bot.
Catches silent crashes, OOM signals, orphan task exceptions, and logs system health.
Import this module early in main.py — it installs global hooks on import.
"""
import asyncio
import gc
import logging
import os
import signal
import sys
import threading
import traceback
from datetime import datetime, timezone

logger = logging.getLogger("nivrael.monitor")

# ─── Force unbuffered output (critical for container logs) ────────────────────
# Without this, Python buffers stdout and logs may be lost when the process is killed.
os.environ["PYTHONUNBUFFERED"] = "1"
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(line_buffering=True)


# ─── 1. Global exception hooks (catch exceptions that escape all try/except) ──

def _global_excepthook(exc_type, exc_value, exc_tb):
    """Catches unhandled exceptions in the main thread."""
    msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    logger.critical("UNHANDLED EXCEPTION (main thread):\n%s", msg)
    sys.stderr.write(f"UNHANDLED EXCEPTION:\n{msg}\n")
    sys.stderr.flush()
    # Call the default hook so the process still exits
    sys.__excepthook__(exc_type, exc_value, exc_tb)

sys.excepthook = _global_excepthook


def _thread_excepthook(args):
    """Catches unhandled exceptions in background threads."""
    msg = "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))
    logger.critical("UNHANDLED EXCEPTION (thread %s):\n%s", args.thread, msg)
    sys.stderr.write(f"UNHANDLED EXCEPTION (thread {args.thread}):\n{msg}\n")
    sys.stderr.flush()

threading.excepthook = _thread_excepthook


# ─── 2. Signal handlers (detect OOM kills, SIGTERM from Coolify, etc.) ────────

def _signal_handler(signum, frame):
    sig_name = signal.Signals(signum).name if hasattr(signal, "Signals") else str(signum)
    stack = "".join(traceback.format_stack(frame)) if frame else "(no stack)"
    msg = (
        f"SIGNAL RECEIVED: {sig_name} (#{signum})\n"
        f"Stack at signal time:\n{stack}"
    )
    logger.critical(msg)
    sys.stderr.write(f"\n{'='*60}\n{msg}\n{'='*60}\n")
    sys.stderr.flush()

    # For SIGTERM, do a graceful shutdown log before exiting
    if signum == signal.SIGTERM:
        logger.critical("SIGTERM received — process will exit. This is likely Coolify/Docker stopping the container.")
        sys.stderr.flush()
        sys.exit(0)

# Install signal handlers (skip on Windows for signals that don't exist)
for sig in (signal.SIGTERM, signal.SIGINT):
    try:
        signal.signal(sig, _signal_handler)
    except (OSError, ValueError):
        pass

# SIGUSR1 is Unix-only — useful for debugging on the VPS
if hasattr(signal, "SIGUSR1"):
    def _debug_signal(signum, frame):
        """Send SIGUSR1 to dump all tasks and memory info."""
        _log_health_snapshot("SIGUSR1 debug dump")
    try:
        signal.signal(signal.SIGUSR1, _debug_signal)
    except (OSError, ValueError):
        pass


# ─── 3. Asyncio exception handler (catches fire-and-forget task crashes) ──────

def install_asyncio_exception_handler(loop=None):
    """Install a custom exception handler on the asyncio event loop.
    Call this after the loop is running (e.g., in post_init).
    """
    if loop is None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.get_event_loop()

    def _asyncio_exception_handler(loop, context):
        exception = context.get("exception")
        message = context.get("message", "")

        if exception:
            tb = "".join(traceback.format_exception(type(exception), exception, exception.__traceback__))
            logger.critical(
                "UNHANDLED ASYNCIO EXCEPTION: %s\nMessage: %s\nTraceback:\n%s",
                type(exception).__name__, message, tb
            )
        else:
            logger.critical("ASYNCIO ERROR (no exception): %s", message)

        # Also log which task caused it
        task = context.get("future")
        if task:
            logger.critical("Task that caused the error: %r", task)

        sys.stderr.flush()

    loop.set_exception_handler(_asyncio_exception_handler)
    logger.info("Asyncio exception handler installed")


# ─── 4. Health monitoring task ────────────────────────────────────────────────

def _get_memory_mb():
    """Get current process memory usage in MB."""
    try:
        # Works on Linux (Docker/VPS)
        with open("/proc/self/status", "r") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024  # KB -> MB
    except (FileNotFoundError, Exception):
        pass
    # Fallback: try psutil
    try:
        import psutil
        return psutil.Process().memory_info().rss / (1024 * 1024)
    except ImportError:
        return -1


def _log_health_snapshot(reason="periodic"):
    """Log a snapshot of system health."""
    mem_mb = _get_memory_mb()
    try:
        loop = asyncio.get_running_loop()
        all_tasks = asyncio.all_tasks(loop)
        task_count = len(all_tasks)
    except RuntimeError:
        task_count = -1
        all_tasks = []

    gc_stats = gc.get_stats()
    gc_summary = ", ".join(f"gen{i}: {s['collections']}c/{s['collected']}obj" for i, s in enumerate(gc_stats))

    logger.info(
        "HEALTH [%s]: memory=%.1fMB | asyncio_tasks=%d | gc=[%s] | pid=%d",
        reason, mem_mb, task_count, gc_summary, os.getpid()
    )

    # If memory is high, log a warning
    if mem_mb > 500:
        logger.warning("HIGH MEMORY USAGE: %.1fMB — possible memory leak!", mem_mb)

    if mem_mb > 1000:
        logger.critical("CRITICAL MEMORY: %.1fMB — OOM kill imminent!", mem_mb)

    # Log tasks that look stuck or suspicious (only if DEBUG)
    if logger.isEnabledFor(logging.DEBUG) and all_tasks:
        for task in all_tasks:
            if not task.done() and task.get_name() != "Task-1":
                logger.debug("  Active task: %s (state=%s)", task.get_name(), task._state)


_HEALTH_INTERVAL_SECONDS = 120  # Log health every 2 minutes
_LAST_CALLBACK_TIME = None
_CALLBACK_COUNT = 0


def track_callback():
    """Call this from the button router to track callback frequency."""
    global _LAST_CALLBACK_TIME, _CALLBACK_COUNT
    _CALLBACK_COUNT += 1
    _LAST_CALLBACK_TIME = datetime.now(timezone.utc)


async def health_watchdog():
    """Background task that periodically logs health metrics."""
    global _CALLBACK_COUNT
    logger.info("Health watchdog started (interval=%ds)", _HEALTH_INTERVAL_SECONDS)
    while True:
        await asyncio.sleep(_HEALTH_INTERVAL_SECONDS)
        _log_health_snapshot("periodic")

        # Log callback throughput
        cbs = _CALLBACK_COUNT
        _CALLBACK_COUNT = 0
        logger.info(
            "THROUGHPUT: %d callbacks in last %ds (%.1f/min)",
            cbs, _HEALTH_INTERVAL_SECONDS, cbs * 60 / _HEALTH_INTERVAL_SECONDS
        )


# ─── 5. DB pool monitoring ────────────────────────────────────────────────────

async def db_pool_monitor():
    """Log DB connection pool stats every 2 minutes."""
    await asyncio.sleep(30)  # Wait for pool to warm up
    while True:
        try:
            from database.db import engine
            from config import DB_POOL_SIZE, DB_MAX_OVERFLOW
            if engine and engine.pool:
                pool = engine.pool
                checked_out = pool.checkedout()
                max_conns = DB_POOL_SIZE + DB_MAX_OVERFLOW
                logger.info(
                    "DB POOL: size=%s | checked_in=%s | checked_out=%s | overflow=%s | max=%s",
                    pool.size(),
                    pool.checkedin(),
                    checked_out,
                    pool.overflow(),
                    max_conns,
                )
                # Warning when pool is getting full (>80%)
                if checked_out > max_conns * 0.8:
                    logger.warning(
                        "DB POOL HIGH USAGE: %d/%d connections checked out (%.0f%%)",
                        checked_out, max_conns, checked_out / max_conns * 100
                    )
                # Critical: all connections in use — deadlock imminent
                if checked_out >= max_conns:
                    logger.critical(
                        "DB POOL EXHAUSTED! All %d/%d connections in use — bot will hang!",
                        checked_out, max_conns
                    )
        except Exception as e:
            logger.warning("DB pool monitor error: %s", e)
        await asyncio.sleep(_HEALTH_INTERVAL_SECONDS)


# ─── 6. Startup banner ───────────────────────────────────────────────────────

def log_startup_info():
    """Log comprehensive startup info for debugging."""
    logger.info("=" * 60)
    logger.info("NIVRAEL BOT STARTING")
    logger.info("=" * 60)
    logger.info("Python: %s", sys.version)
    logger.info("PID: %d", os.getpid())
    logger.info("CWD: %s", os.getcwd())
    logger.info("Memory at start: %.1fMB", _get_memory_mb())

    # Log environment hints (not secrets)
    logger.info("WEBHOOK_URL set: %s", bool(os.getenv("WEBHOOK_URL")))
    logger.info("DATABASE_URL set: %s", bool(os.getenv("DATABASE_URL")))
    logger.info("PYTHONUNBUFFERED: %s", os.getenv("PYTHONUNBUFFERED", "not set"))
    logger.info("=" * 60)
