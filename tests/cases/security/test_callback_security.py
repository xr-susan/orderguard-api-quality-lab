from __future__ import annotations

import json

import pytest


@pytest.mark.security
def test_callback_with_invalid_signature_cannot_mutate_an_order(
    api_client, order_client, merchant_order_no: str, idempotency_key: str
) -> None:
    created = order_client.create(
        merchant_order_no=merchant_order_no,
        sku="SKU-001",
        quantity=1,
        idempotency_key=idempotency_key,
    )
    assert created.status_code == 201
    body = json.dumps(
        {
            "merchant_order_no": merchant_order_no,
            "payment_id": "forged-payment",
            "status": "succeeded",
        },
        separators=(",", ":"),
    )

    callback = api_client.post(
        "/payments/callback",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Payment-Signature": "forged",
        },
    )
    order = order_client.get(created.json()["id"])

    assert callback.status_code == 401
    assert order.json()["status"] == "CREATED"
