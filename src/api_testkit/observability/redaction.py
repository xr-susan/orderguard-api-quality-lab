"""Centralised recursive redaction for logs and report attachments."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

REDACTED = "***REDACTED***"

_SENSITIVE_PARTS = (
    "authorization",
    "cookie",
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "signature",
    "card_number",
    "cardnumber",
    "cvv",
)
_BEARER_PATTERN = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+\-/]+=*")
_KEY_VALUE_PATTERN = re.compile(
    r"(?i)(authorization|cookie|password|passwd|secret|token|api[_-]?key|signature|cvv)"
    r"(\s*[=:]\s*)([^\s,;}&]+)"
)


def is_sensitive_key(key: object) -> bool:
    normalised = str(key).lower().replace("-", "_")
    return any(part in normalised for part in _SENSITIVE_PARTS)


def redact(value: Any, *, key: object | None = None) -> Any:
    """Return a recursively redacted copy without mutating the input."""

    if key is not None and is_sensitive_key(key):
        return REDACTED
    if isinstance(value, Mapping):
        return {str(item_key): redact(item, key=item_key) for item_key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(redact(item) for item in value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [redact(item) for item in value]
    if isinstance(value, bytes):
        return redact_text(value.decode("utf-8", errors="replace"))
    if isinstance(value, str):
        return redact_text(value)
    return value


def redact_headers(headers: Mapping[str, Any]) -> dict[str, Any]:
    return {name: redact(value, key=name) for name, value in headers.items()}


def redact_url(url: str) -> str:
    """Redact sensitive query parameters while retaining useful routing data."""

    try:
        parts = urlsplit(url)
        query = [
            (name, REDACTED if is_sensitive_key(name) else value)
            for name, value in parse_qsl(parts.query, keep_blank_values=True)
        ]
        return urlunsplit(
            (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
        )
    except ValueError:
        return redact_text(url)


def redact_text(value: str) -> str:
    value = _BEARER_PATTERN.sub(f"Bearer {REDACTED}", value)
    return _KEY_VALUE_PATTERN.sub(
        lambda match: f"{match.group(1)}{match.group(2)}{REDACTED}", value
    )


__all__ = [
    "REDACTED",
    "is_sensitive_key",
    "redact",
    "redact_headers",
    "redact_text",
    "redact_url",
]
