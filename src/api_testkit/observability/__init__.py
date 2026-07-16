"""Correlation context, redacted logging, and optional Allure reporting."""

from api_testkit.observability.allure_adapter import AllureAdapter
from api_testkit.observability.context import (
    ExecutionContext,
    bind_context,
    get_context,
)
from api_testkit.observability.logging import configure_logging
from api_testkit.observability.redaction import (
    REDACTED,
    redact,
    redact_headers,
    redact_text,
    redact_url,
)

__all__ = [
    "REDACTED",
    "AllureAdapter",
    "ExecutionContext",
    "bind_context",
    "configure_logging",
    "get_context",
    "redact",
    "redact_headers",
    "redact_text",
    "redact_url",
]
