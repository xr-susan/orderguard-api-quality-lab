"""Standard-library logging with correlation fields and safe messages."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any, ClassVar, TextIO

from api_testkit.observability.context import get_context
from api_testkit.observability.redaction import redact, redact_text


class ContextFilter(logging.Filter):
    """Inject contextvars into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        context = get_context()
        record.run_id = context.run_id
        record.case_id = context.case_id
        record.request_id = context.request_id
        record.retry_attempt = context.retry_attempt
        return True


class RedactingFilter(logging.Filter):
    """Render then redact a record so positional arguments cannot bypass rules."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_text(record.getMessage())
        record.args = ()
        for name, value in tuple(record.__dict__.items()):
            if name not in logging.makeLogRecord({}).__dict__:
                record.__dict__[name] = redact(value, key=name)
        return True


class JsonFormatter(logging.Formatter):
    """One-line JSON logs suitable for CI artifacts and local diagnosis."""

    _STANDARD_FIELDS: ClassVar[set[str]] = {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
        "taskName",
    }

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "run_id": getattr(record, "run_id", None),
            "case_id": getattr(record, "case_id", None),
            "request_id": getattr(record, "request_id", None),
            "retry_attempt": getattr(record, "retry_attempt", None),
        }
        for name, value in record.__dict__.items():
            if name not in self._STANDARD_FIELDS and name not in payload:
                payload[name] = redact(value, key=name)
        if record.exc_info:
            payload["exception"] = redact_text(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False, default=str, separators=(",", ":"))


def configure_logging(
    *,
    level: str | int = "INFO",
    stream: TextIO | None = None,
    logger: logging.Logger | None = None,
    replace_handlers: bool = True,
) -> logging.Logger:
    """Configure a logger with JSON output and redaction filters."""

    target = logger or logging.getLogger("api_testkit")
    target.setLevel(level)
    target.propagate = False
    if replace_handlers:
        target.handlers.clear()
    handler = logging.StreamHandler(stream or sys.stderr)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(ContextFilter())
    handler.addFilter(RedactingFilter())
    target.addHandler(handler)
    return target


__all__ = [
    "ContextFilter",
    "JsonFormatter",
    "RedactingFilter",
    "configure_logging",
]
