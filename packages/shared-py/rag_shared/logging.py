"""Shared JSON logging configuration.

Default: stdout (captured by docker logs / make log).
Optional: rotating file handler when ``log_file`` is provided. Each module
typically passes ``os.getenv("LOG_FILE_PATH")``; the path is bind-mounted
to ``data/logs/<module>/`` on the host so logs persist across container
restarts and are visible to the operator without docker inspect.
"""
import json
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from typing import Optional


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps({
            "level": record.levelname,
            "service": getattr(record, "service", "unknown"),
            "msg": record.getMessage(),
            "ts": self.formatTime(record),
        })


def _make_stdout_handler(formatter: logging.Formatter) -> logging.Handler:
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(formatter)
    return h


def _make_file_handler(path: str, formatter: logging.Formatter) -> Optional[logging.Handler]:
    """Build a rotating file handler.

    Soft-fails to None when the directory or permissions are wrong, unless
    LOG_FILE_REQUIRED=1 — in which case startup raises so misconfiguration
    is caught immediately rather than silently dropping logs.

    Sizing/retention is tunable via LOG_MAX_BYTES (default 10MB) and
    LOG_BACKUP_COUNT (default 5).

    Caller's responsibility: when running multi-worker uvicorn, do NOT use
    this handler — RotatingFileHandler is not process-safe and rotation
    will lose log lines. Run one worker per container or stream stdout to
    a sidecar log shipper instead.
    """
    max_bytes = int(os.getenv("LOG_MAX_BYTES", str(10 * 1024 * 1024)))
    backup_count = int(os.getenv("LOG_BACKUP_COUNT", "5"))
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        h = RotatingFileHandler(
            path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        h.setFormatter(formatter)
        return h
    except OSError as e:
        msg = f"[logging] file handler disabled for {path}: {e}"
        if os.getenv("LOG_FILE_REQUIRED", "0") == "1":
            raise RuntimeError(msg) from e
        sys.stderr.write(msg + "\n")
        return None


def setup_logging(
    service_name: str,
    level: int = logging.INFO,
    log_file: Optional[str] = None,
) -> None:
    """Configure JSON logging.

    - stdout handler is always installed.
    - If ``log_file`` is non-empty, a 10MB × 5 rotating file handler is added.
      Failures (missing dir, no perms) are logged to stderr and the file
      handler is silently skipped — stdout still works.
    """
    formatter = JsonFormatter()
    handlers: list[logging.Handler] = [_make_stdout_handler(formatter)]

    if log_file:
        fh = _make_file_handler(log_file, formatter)
        if fh is not None:
            handlers.append(fh)

    root = logging.getLogger()
    root.handlers = handlers
    root.setLevel(level)
    # Attach service name to all records via a filter (idempotent on re-setup)
    root.filters = [f for f in root.filters if getattr(f, "_rag_shared_service_filter", False) is False]
    service_filter = lambda r: setattr(r, "service", service_name) or True  # noqa: E731
    setattr(service_filter, "_rag_shared_service_filter", True)
    root.addFilter(service_filter)
