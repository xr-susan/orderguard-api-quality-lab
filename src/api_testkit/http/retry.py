"""Tenacity policy helpers for safe, bounded HTTP retries."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx
from tenacity import RetryCallState

DEFAULT_RETRY_STATUS_CODES = frozenset({429, 502, 503, 504})
SAFE_RETRY_METHODS = frozenset({"GET", "HEAD"})


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Controls which requests can retry and how long they may do so."""

    enabled: bool = True
    max_attempts: int = 3
    total_budget: float = 10.0
    base_wait: float = 0.25
    max_wait: float = 3.0
    jitter: float = 0.1
    retry_status_codes: frozenset[int] = field(default_factory=lambda: DEFAULT_RETRY_STATUS_CODES)

    def __post_init__(self) -> None:
        if not 1 <= self.max_attempts <= 10:
            raise ValueError("max_attempts must be between 1 and 10")
        if self.total_budget <= 0:
            raise ValueError("total_budget must be positive")
        if self.base_wait < 0 or self.max_wait < self.base_wait or self.jitter < 0:
            raise ValueError("retry waits must satisfy 0 <= base_wait <= max_wait and jitter >= 0")

    @classmethod
    def from_settings(cls, settings: Any) -> RetryPolicy:
        """Create a policy from a compatible Pydantic settings object."""

        return cls(
            enabled=bool(settings.enabled),
            max_attempts=int(settings.max_attempts),
            total_budget=float(settings.total_budget),
            base_wait=float(settings.base_wait),
            max_wait=float(settings.max_wait),
            jitter=float(settings.jitter),
            retry_status_codes=frozenset(settings.retry_status_codes),
        )


def _contains_header(headers: httpx.Headers | dict[str, str], name: str) -> bool:
    needle = name.lower()
    return any(str(key).lower() == needle and bool(value) for key, value in headers.items())


def is_method_retryable(method: str, headers: httpx.Headers | dict[str, str] | None = None) -> bool:
    """Return whether automatic replay is safe under the framework policy."""

    normalised = method.upper()
    if normalised in SAFE_RETRY_METHODS:
        return True
    return normalised == "POST" and _contains_header(headers or {}, "Idempotency-Key")


def is_transport_retryable(exc: BaseException) -> bool:
    """Limit retries to network I/O failures and explicit timeouts."""

    return isinstance(exc, (httpx.NetworkError, httpx.TimeoutException))


def is_response_retryable(response: httpx.Response, policy: RetryPolicy) -> bool:
    return response.status_code in policy.retry_status_codes


def parse_retry_after(value: str | None, *, now: datetime | None = None) -> float | None:
    """Parse an RFC Retry-After delta or HTTP date into non-negative seconds."""

    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    try:
        seconds = float(stripped)
    except ValueError:
        try:
            target = parsedate_to_datetime(stripped)
        except (TypeError, ValueError, OverflowError):
            return None
        if target.tzinfo is None:
            target = target.replace(tzinfo=UTC)
        current = now or datetime.now(tz=UTC)
        seconds = (target - current).total_seconds()
    return max(0.0, seconds)


class RetryWait:
    """Tenacity wait strategy preferring server-provided Retry-After."""

    def __init__(
        self,
        policy: RetryPolicy,
        *,
        random_source: random.Random | None = None,
    ) -> None:
        self.policy = policy
        self.random_source = random_source or random.Random()

    def __call__(self, retry_state: RetryCallState) -> float:
        outcome = retry_state.outcome
        if outcome is not None and not outcome.failed:
            result = outcome.result()
            if isinstance(result, httpx.Response):
                server_wait = parse_retry_after(result.headers.get("Retry-After"))
                if server_wait is not None:
                    return server_wait
        exponent = max(0, retry_state.attempt_number - 1)
        # 2.0 ** int is typed float by mypy; `2 ** int` is typed Any, which would
        # poison the min() below and trip --strict's no-any-return.
        backoff = self.policy.base_wait * (2.0**exponent)
        delay = min(self.policy.max_wait, backoff)
        if self.policy.jitter:
            delay += self.random_source.uniform(0.0, self.policy.jitter)
        return delay


__all__ = [
    "DEFAULT_RETRY_STATUS_CODES",
    "SAFE_RETRY_METHODS",
    "RetryPolicy",
    "RetryWait",
    "is_method_retryable",
    "is_response_retryable",
    "is_transport_retryable",
    "parse_retry_after",
]
