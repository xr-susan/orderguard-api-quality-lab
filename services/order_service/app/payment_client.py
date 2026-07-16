"""Payment dependency client with bounded, observable retries."""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from time import perf_counter
from typing import Any

import httpx

from .config import Settings

RETRYABLE_STATUS_CODES = frozenset({429, 502, 503, 504})


@dataclass(frozen=True)
class AttemptRecord:
    attempt_number: int
    outcome: str
    status_code: int | None
    retryable: bool
    elapsed_ms: int
    error_type: str | None = None


@dataclass(frozen=True)
class PaymentResult:
    payment_id: str | None
    status: str
    attempts: tuple[AttemptRecord, ...]
    payload: Mapping[str, Any]


class PaymentServiceError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        attempts: list[AttemptRecord],
        *,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.attempts = tuple(attempts)
        self.status_code = status_code


class PaymentClient:
    """Calls the payment service and retries only known transient failures."""

    def __init__(
        self,
        settings: Settings,
        *,
        http_client: httpx.AsyncClient | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        random_value: Callable[[], float] = random.random,
    ) -> None:
        self._settings = settings
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(settings.payment_timeout_seconds)
        )
        self._sleep = sleep
        self._random_value = random_value

    async def create_payment(
        self,
        *,
        merchant_order_no: str,
        amount: float,
        currency: str,
        callback_url: str,
        idempotency_key: str,
    ) -> PaymentResult:
        attempts: list[AttemptRecord] = []
        url = f"{self._settings.payment_base_url.rstrip('/')}/payments"
        body = {
            "merchant_order_no": merchant_order_no,
            "amount": amount,
            "currency": currency,
            "callback_url": callback_url,
        }
        headers = {"Idempotency-Key": idempotency_key}

        for attempt_number in range(1, self._settings.payment_max_attempts + 1):
            started = perf_counter()
            try:
                response = await self._client.post(url, json=body, headers=headers)
            except httpx.TimeoutException as exc:
                attempts.append(
                    AttemptRecord(
                        attempt_number=attempt_number,
                        outcome="timeout",
                        status_code=None,
                        retryable=True,
                        elapsed_ms=self._elapsed_ms(started),
                        error_type=type(exc).__name__,
                    )
                )
                if attempt_number == self._settings.payment_max_attempts:
                    raise PaymentServiceError(
                        "PAYMENT_TIMEOUT",
                        "Payment service timed out after bounded retries",
                        attempts,
                    ) from exc
                await self._sleep(self._fallback_delay(attempt_number))
                continue
            except httpx.TransportError as exc:
                attempts.append(
                    AttemptRecord(
                        attempt_number=attempt_number,
                        outcome="transport_error",
                        status_code=None,
                        retryable=True,
                        elapsed_ms=self._elapsed_ms(started),
                        error_type=type(exc).__name__,
                    )
                )
                if attempt_number == self._settings.payment_max_attempts:
                    raise PaymentServiceError(
                        "PAYMENT_UNAVAILABLE",
                        "Payment service is unavailable after bounded retries",
                        attempts,
                    ) from exc
                await self._sleep(self._fallback_delay(attempt_number))
                continue

            retryable = response.status_code in RETRYABLE_STATUS_CODES
            attempts.append(
                AttemptRecord(
                    attempt_number=attempt_number,
                    outcome="response",
                    status_code=response.status_code,
                    retryable=retryable,
                    elapsed_ms=self._elapsed_ms(started),
                )
            )

            if retryable and attempt_number < self._settings.payment_max_attempts:
                await self._sleep(self._retry_delay(response, attempt_number))
                continue
            if retryable:
                raise PaymentServiceError(
                    "PAYMENT_UNAVAILABLE",
                    "Payment service returned a transient error after bounded retries",
                    attempts,
                    status_code=response.status_code,
                )
            if not 200 <= response.status_code < 300:
                raise PaymentServiceError(
                    "PAYMENT_REJECTED",
                    "Payment service rejected the request",
                    attempts,
                    status_code=response.status_code,
                )
            try:
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ValueError("response is not an object")
            except (ValueError, TypeError) as exc:
                raise PaymentServiceError(
                    "INVALID_PAYMENT_RESPONSE",
                    "Payment service returned invalid JSON",
                    attempts,
                    status_code=response.status_code,
                ) from exc

            return PaymentResult(
                payment_id=self._optional_string(payload.get("payment_id")),
                status=str(payload.get("status", "PENDING")).strip().upper(),
                attempts=tuple(attempts),
                payload=payload,
            )

        raise AssertionError("unreachable payment retry state")

    @staticmethod
    def _optional_string(value: Any) -> str | None:
        return str(value) if value is not None else None

    @staticmethod
    def _elapsed_ms(started: float) -> int:
        return max(0, round((perf_counter() - started) * 1000))

    def _fallback_delay(self, attempt_number: int) -> float:
        base = self._settings.payment_retry_base_delay_seconds * (2 ** (attempt_number - 1))
        jitter = self._settings.payment_retry_base_delay_seconds * self._random_value()
        return min(base + jitter, self._settings.payment_retry_max_delay_seconds)

    def _retry_delay(self, response: httpx.Response, attempt_number: int) -> float:
        retry_after = response.headers.get("Retry-After")
        parsed = self._parse_retry_after(retry_after) if retry_after else None
        if parsed is not None:
            return min(parsed, self._settings.payment_retry_max_delay_seconds)
        return self._fallback_delay(attempt_number)

    @staticmethod
    def _parse_retry_after(value: str) -> float | None:
        try:
            return max(0.0, float(value))
        except ValueError:
            try:
                parsed = parsedate_to_datetime(value)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=UTC)
                return max(0.0, (parsed - datetime.now(UTC)).total_seconds())
            except (TypeError, ValueError, OverflowError):
                return None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
