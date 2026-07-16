from __future__ import annotations

import hashlib
import hmac
import json

from fastapi.testclient import TestClient

from services.order_service.app.payment_client import (
    AttemptRecord,
    PaymentServiceError,
)
from services.order_service.tests.conftest import FakePaymentClient, create_order


def test_health_and_seed_products(client: TestClient) -> None:
    assert client.get("/health").json() == {
        "status": "ok",
        "service": "order-service",
    }
    products = client.get("/products")
    assert products.status_code == 200
    assert [item["sku"] for item in products.json()] == ["SKU-001", "SKU-002", "SKU-003"]


def test_auth_rejects_bad_credentials(client: TestClient) -> None:
    response = client.post(
        "/auth/token",
        json={"username": "demo", "password": "wrong"},
    )
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "INVALID_CREDENTIALS"


def test_create_order_is_idempotent_without_double_reserving_stock(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    first = create_order(client, auth_headers)
    replay = create_order(client, auth_headers)

    assert first.status_code == 201
    assert replay.status_code == 200
    assert replay.headers["Idempotent-Replayed"] == "true"
    assert replay.json()["id"] == first.json()["id"]
    product = next(item for item in client.get("/products").json() if item["sku"] == "SKU-001")
    assert product["available_stock"] == 18


def test_create_order_rejects_same_key_with_different_payload(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    assert create_order(client, auth_headers).status_code == 201
    conflict = create_order(
        client,
        auth_headers,
        merchant_order_no="ORDER-002",
        idempotency_key="create-key-001",
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "IDEMPOTENCY_KEY_REUSED"


def test_successful_payment_records_attempt_and_replays_safely(
    client: TestClient,
    auth_headers: dict[str, str],
    fake_payment: FakePaymentClient,
) -> None:
    order = create_order(client, auth_headers).json()
    headers = {**auth_headers, "Idempotency-Key": "pay-key-001"}

    paid = client.post(f"/orders/{order['id']}/pay", headers=headers)
    replay = client.post(f"/orders/{order['id']}/pay", headers=headers)

    assert paid.status_code == 200
    assert paid.json()["status"] == "PAID"
    assert paid.json()["payment_attempts"][0]["status_code"] == 201
    assert replay.status_code == 200
    assert replay.headers["Idempotent-Replayed"] == "true"
    assert fake_payment.calls == 1


def test_signed_callback_completes_pending_payment(
    client: TestClient,
    auth_headers: dict[str, str],
    fake_payment: FakePaymentClient,
) -> None:
    fake_payment.status = "PENDING"
    order = create_order(client, auth_headers).json()
    pending = client.post(
        f"/orders/{order['id']}/pay",
        headers={**auth_headers, "Idempotency-Key": "pay-key-002"},
    )
    assert pending.json()["status"] == "PAYING"

    raw_body = json.dumps(
        {
            "merchant_order_no": order["merchant_order_no"],
            "payment_id": fake_payment.payment_id,
            "status": "succeeded",
        },
        separators=(",", ":"),
    ).encode()
    signature = hmac.new(b"test-callback-secret-value", raw_body, hashlib.sha256).hexdigest()
    callback = client.post(
        "/payments/callback",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-Payment-Signature": f"sha256={signature}",
        },
    )
    duplicate = client.post(
        "/payments/callback",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-Payment-Signature": signature,
        },
    )

    assert callback.status_code == 200
    assert callback.json()["status"] == "PAID"
    assert duplicate.status_code == 200
    assert duplicate.json()["status"] == "PAID"


def test_invalid_callback_signature_is_rejected(
    client: TestClient,
) -> None:
    response = client.post(
        "/payments/callback",
        json={
            "merchant_order_no": "ORDER-001",
            "payment_id": "pay_001",
            "status": "PAID",
        },
        headers={"X-Payment-Signature": "wrong"},
    )
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "INVALID_SIGNATURE"


def test_exhausted_payment_retries_release_inventory(
    client: TestClient,
    auth_headers: dict[str, str],
    fake_payment: FakePaymentClient,
) -> None:
    async def fail_payment(**_request: object):
        fake_payment.calls += 1
        attempts = [AttemptRecord(number, "response", 503, True, 1) for number in range(1, 4)]
        raise PaymentServiceError("PAYMENT_UNAVAILABLE", "dependency down", attempts)

    fake_payment.create_payment = fail_payment  # type: ignore[method-assign]
    order = create_order(client, auth_headers, quantity=3).json()
    failed = client.post(
        f"/orders/{order['id']}/pay",
        headers={**auth_headers, "Idempotency-Key": "pay-key-failure"},
    )
    persisted = client.get(f"/orders/{order['id']}", headers=auth_headers)
    product = next(item for item in client.get("/products").json() if item["sku"] == "SKU-001")

    assert failed.status_code == 502
    assert persisted.json()["status"] == "PAYMENT_FAILED"
    assert persisted.json()["reservation_released"] is True
    assert len(persisted.json()["payment_attempts"]) == 3
    assert product["available_stock"] == 20


def test_reset_restores_seed_state(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    create_order(client, auth_headers, quantity=5)
    assert client.post("/__test__/reset").status_code == 200
    product = next(item for item in client.get("/products").json() if item["sku"] == "SKU-001")
    assert product["available_stock"] == 20
