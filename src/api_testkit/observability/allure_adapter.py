"""Optional, bounded, redacted Allure integration.

Importing the framework must remain safe when ``allure-pytest`` is not
installed, which is useful for lightweight framework unit-test jobs.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from typing import Any

from api_testkit.observability.redaction import redact, redact_text

try:  # pragma: no cover - depends on the optional report extra
    import allure as _allure
except ImportError:  # pragma: no cover - the default in minimal environments
    _allure = None


class AllureAdapter:
    """Small facade that turns into a no-op without Allure installed."""

    def __init__(self, *, enabled: bool = True, max_attachment_bytes: int = 256_000) -> None:
        if max_attachment_bytes < 1:
            raise ValueError("max_attachment_bytes must be positive")
        self.enabled = enabled and _allure is not None
        self.max_attachment_bytes = max_attachment_bytes

    @property
    def available(self) -> bool:
        return _allure is not None

    def _bounded(self, value: str) -> str:
        encoded = value.encode("utf-8")
        if len(encoded) <= self.max_attachment_bytes:
            return value
        suffix = b"\n... [attachment truncated by api_testkit]"
        limit = max(0, self.max_attachment_bytes - len(suffix))
        return (encoded[:limit] + suffix).decode("utf-8", errors="ignore")

    def attach_text(self, name: str, value: str) -> None:
        if not self.enabled:
            return
        assert _allure is not None
        _allure.attach(
            self._bounded(redact_text(value)),
            name=name,
            attachment_type=_allure.attachment_type.TEXT,
        )

    def attach_json(self, name: str, value: Any) -> None:
        if not self.enabled:
            return
        assert _allure is not None
        body = json.dumps(redact(value), ensure_ascii=False, indent=2, default=str)
        _allure.attach(
            self._bounded(body),
            name=name,
            attachment_type=_allure.attachment_type.JSON,
        )

    @contextmanager
    def step(self, title: str) -> Iterator[None]:
        context = _allure.step(title) if self.enabled and _allure is not None else nullcontext()
        with context:
            yield


__all__ = ["AllureAdapter"]
