from __future__ import annotations

from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient

from services.order_service.app.config import Settings
from services.order_service.app.main import create_app
from services.order_service.app.payment_client import AttemptRecord, PaymentResult


@dataclass
class FakePaymentClient:
    status: str = "SUCCEEDED"
    payment_id: str = "pay_test_001"
    calls: int = 0

    async def create_payment(self, **_request: object) -> PaymentResult:
        self.calls += 1
        return PaymentResult(
            payment_id=self.payment_id,
            status=self.status,
            attempts=(
                AttemptRecord(
                    attempt_number=1,
                    outcome="response",
                    status_code=201,
                    retryable=False,
                    elapsed_ms=2,
                ),
            ),
            payload={"payment_id": self.payment_id, "status": self.status},
        )


@pytest.fixture
def fake_payment() -> FakePaymentClient:
    return FakePaymentClient()


@pytest.fixture
def client(tmp_path, fake_payment: FakePaymentClient) -> TestClient:
    settings = Settings(
        APP_ENV="test",
        ORDER_DATABASE_URL=f"sqlite:///{tmp_path / 'orders.db'}",
        PAYMENT_BASE_URL="http://payment.test",
        ORDER_PUBLIC_BASE_URL="http://orders.test",
        PAYMENT_CALLBACK_SECRET="test-callback-secret-value",
        AUTH_SECRET="test-auth-secret-value",
        PAYMENT_RETRY_BASE_DELAY_SECONDS=0,
    )
    application = create_app(settings, payment_client=fake_payment)
    with TestClient(application) as test_client:
        yield test_client


@pytest.fixture
def auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/auth/token",
        json={"username": "demo", "password": "demo123"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def create_order(
    client: TestClient,
    auth_headers: dict[str, str],
    *,
    merchant_order_no: str = "ORDER-001",
    idempotency_key: str = "create-key-001",
    quantity: int = 2,
):
    return client.post(
        "/orders",
        headers={**auth_headers, "Idempotency-Key": idempotency_key},
        json={
            "merchant_order_no": merchant_order_no,
            "sku": "SKU-001",
            "quantity": quantity,
        },
    )
