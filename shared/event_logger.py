"""Centralized Event Logging Service.

Provides structured, module-aware logging that writes to both
Python logging (stderr) and the `event_log` DB table.

Usage:
    from shared.event_logger import get_event_logger

    elog = get_event_logger("pipeline")
    elog.info("Document parsed", doc_id=42, details={"pages": 10})
    elog.error("Embedding failed", doc_id=42, error=e)

    # Timed operations
    with elog.timed("embed_chunks", doc_id=42):
        embeddings = embed(texts)

    # Access trace_id for request correlation
    from shared.event_logger import get_trace_id, set_trace_id
"""

import logging
import traceback
import uuid
from contextvars import ContextVar
from contextlib import contextmanager
from datetime import datetime, timezone
from time import perf_counter
from typing import Any

_trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")
_user_id_var: ContextVar[int | None] = ContextVar("user_id", default=None)
_ip_var: ContextVar[str] = ContextVar("ip_address", default="")


# ─── Context Management ──────────────────────────────────────────────────────

def new_trace_id() -> str:
    return uuid.uuid4().hex[:16]


def get_trace_id() -> str:
    return _trace_id_var.get()


def set_trace_id(trace_id: str) -> None:
    _trace_id_var.set(trace_id)


def set_request_context(*, trace_id: str | None = None,
                        user_id: int | None = None,
                        ip_address: str = "") -> str:
    """Set per-request context. Returns the trace_id used."""
    tid = trace_id or new_trace_id()
    _trace_id_var.set(tid)
    _user_id_var.set(user_id)
    _ip_var.set(ip_address)
    return tid


# ─── DB Writer ────────────────────────────────────────────────────────────────

def _write_event_to_db(
    module: str,
    event_type: str,
    severity: str,
    message: str,
    user_id: int | None = None,
    session_id: int | None = None,
    doc_id: int | None = None,
    details: dict | None = None,
    duration_ms: int | None = None,
    trace_id: str = "",
    ip_address: str = "",
) -> None:
    """Best-effort write to event_log table. Never raises."""
    try:
        from shared.db import get_session
        from shared.models.orm import EventLog

        with get_session() as session:
            session.add(EventLog(
                trace_id=trace_id or get_trace_id(),
                module=module,
                event_type=event_type,
                severity=severity,
                user_id=user_id or _user_id_var.get(),
                session_id=session_id,
                doc_id=doc_id,
                message=message[:2000],
                details=details,
                duration_ms=duration_ms,
                ip_address=ip_address or _ip_var.get(),
            ))
    except Exception:
        # Never let logging break the application
        logging.getLogger(__name__).debug("Failed to write event_log", exc_info=True)


# ─── EventLogger ──────────────────────────────────────────────────────────────

class EventLogger:
    """Module-specific structured event logger.

    Writes to both Python logging and the event_log DB table.
    """

    def __init__(self, module: str):
        self.module = module
        self._logger = logging.getLogger(f"rag.{module}")

    # --- Severity Methods ---

    def debug(self, message: str, **kwargs: Any) -> None:
        self._log("debug", "info", message, **kwargs)

    def info(self, message: str, **kwargs: Any) -> None:
        self._log("info", "info", message, **kwargs)

    def warning(self, message: str, **kwargs: Any) -> None:
        self._log("warning", "warning", message, **kwargs)

    def error(self, message: str, *, error: BaseException | None = None, **kwargs: Any) -> None:
        if error:
            kwargs.setdefault("details", {})
            kwargs["details"]["error_type"] = type(error).__name__
            kwargs["details"]["error_message"] = str(error)[:1000]
            kwargs["details"]["traceback"] = traceback.format_exc()[-2000:]
        self._log("error", "error", message, **kwargs)

    def critical(self, message: str, *, error: BaseException | None = None, **kwargs: Any) -> None:
        if error:
            kwargs.setdefault("details", {})
            kwargs["details"]["error_type"] = type(error).__name__
            kwargs["details"]["error_message"] = str(error)[:1000]
        self._log("critical", "error", message, **kwargs)

    # --- Typed Event Methods ---

    def stage_start(self, stage: str, **kwargs: Any) -> None:
        self._log("info", "stage_start", f"Stage started: {stage}",
                  details={**kwargs.pop("details", {}), "stage": stage}, **kwargs)

    def stage_end(self, stage: str, duration_ms: int | None = None, **kwargs: Any) -> None:
        self._log("info", "stage_end", f"Stage completed: {stage}",
                  details={**kwargs.pop("details", {}), "stage": stage},
                  duration_ms=duration_ms, **kwargs)

    def stage_fail(self, stage: str, error: BaseException, **kwargs: Any) -> None:
        kwargs.setdefault("details", {})
        kwargs["details"]["stage"] = stage
        kwargs["details"]["error_type"] = type(error).__name__
        kwargs["details"]["error_message"] = str(error)[:1000]
        self._log("error", "stage_fail", f"Stage failed: {stage}", **kwargs)

    def request(self, method: str, path: str, **kwargs: Any) -> None:
        self._log("info", "request", f"{method} {path}", **kwargs)

    def response(self, method: str, path: str, status_code: int,
                 duration_ms: int | None = None, **kwargs: Any) -> None:
        self._log("info", "response", f"{method} {path} → {status_code}",
                  duration_ms=duration_ms, **kwargs)

    # --- Timed Context Manager ---

    @contextmanager
    def timed(self, operation: str, **kwargs: Any):
        """Context manager that logs start/end with duration.

        Usage:
            with elog.timed("embed_chunks", doc_id=42):
                embeddings = embed(texts)
        """
        self.stage_start(operation, **kwargs)
        start = perf_counter()
        try:
            yield
        except Exception as e:
            elapsed = int((perf_counter() - start) * 1000)
            self.stage_fail(operation, e, duration_ms=elapsed, **kwargs)
            raise
        else:
            elapsed = int((perf_counter() - start) * 1000)
            self.stage_end(operation, duration_ms=elapsed, **kwargs)

    # --- Internal ---

    def _log(self, severity: str, event_type: str, message: str,
             user_id: int | None = None, session_id: int | None = None,
             doc_id: int | None = None, details: dict | None = None,
             duration_ms: int | None = None, **extra: Any) -> None:
        # Merge any extra kwargs into details
        if extra:
            details = {**(details or {}), **extra}

        # Python logging
        log_fn = getattr(self._logger, severity, self._logger.info)
        ctx_parts = []
        if doc_id:
            ctx_parts.append(f"doc={doc_id}")
        if session_id:
            ctx_parts.append(f"session={session_id}")
        if duration_ms is not None:
            ctx_parts.append(f"{duration_ms}ms")
        ctx = f" [{', '.join(ctx_parts)}]" if ctx_parts else ""
        log_fn(f"[{self.module}]{ctx} {message}")

        # DB write (best-effort, non-blocking)
        _write_event_to_db(
            module=self.module,
            event_type=event_type,
            severity=severity,
            message=message,
            user_id=user_id,
            session_id=session_id,
            doc_id=doc_id,
            details=details,
            duration_ms=duration_ms,
        )


# ─── Module Registry ──────────────────────────────────────────────────────────

_loggers: dict[str, EventLogger] = {}


def get_event_logger(module: str) -> EventLogger:
    """Get or create an EventLogger for the given module.

    Standard modules: pipeline, serving, sync, system, mineru
    """
    if module not in _loggers:
        _loggers[module] = EventLogger(module)
    return _loggers[module]
