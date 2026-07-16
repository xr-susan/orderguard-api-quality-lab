from __future__ import annotations

import asyncio

import httpx

from services.order_service.app.config import Settings
from services.order_service.app.payment_client import PaymentClient


def test_payment_client_retries_transient_status_and_preserves_idempotency_key() -> None:
    seen_keys: list[str] = []
    responses = iter(
        [
            httpx.Response(429, headers={"Retry-After": "0.25"}, json={"error": "slow down"}),
            httpx.Response(503, json={"error": "temporarily unavailable"}),
            httpx.Response(201, json={"payment_id": "pay_stable", "status": "SUCCEEDED"}),
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        seen_keys.append(request.headers["Idempotency-Key"])
        return next(responses)

    delays: list[float] = []

    async def record_delay(delay: float) -> None:
        delays.append(delay)

    async def scenario() -> None:
        settings = Settings(
            APP_ENV="test",
            ORDER_DATABASE_URL="sqlite://",
            PAYMENT_BASE_URL="http://payment.test",
            ORDER_PUBLIC_BASE_URL="http://orders.test",
            PAYMENT_CALLBACK_SECRET="test-callback-secret-value",
            AUTH_SECRET="test-auth-secret-value",
            PAYMENT_MAX_ATTEMPTS=3,
            PAYMENT_RETRY_BASE_DELAY_SECONDS=0.1,
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = PaymentClient(
                settings,
                http_client=http_client,
                sleep=record_delay,
                random_value=lambda: 0,
            )
            result = await client.create_payment(
                merchant_order_no="ORDER-RETRY",
                amount=79.99,
                currency="USD",
                callback_url="http://orders.test/payments/callback",
                idempotency_key="stable-key",
            )

        assert result.payment_id == "pay_stable"
        assert [attempt.status_code for attempt in result.attempts] == [429, 503, 201]

    asyncio.run(scenario())

    assert seen_keys == ["stable-key", "stable-key", "stable-key"]
    assert delays == [0.25, 0.2]
