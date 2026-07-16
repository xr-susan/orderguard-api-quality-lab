from __future__ import annotations

import pytest

from tests.support.assertions import assert_order_state


@pytest.mark.smoke
def test_customer_can_create_and_pay_an_order(
    order_client, merchant_order_no: str, idempotency_key: str
) -> None:
    created = order_client.create(
        merchant_order_no=merchant_order_no,
        sku="SKU-001",
        quantity=1,
        idempotency_key=idempotency_key,
    )
    assert created.status_code == 201, created.text

    paid = order_client.pay(created.json()["id"], idempotency_key=f"pay-{idempotency_key}")

    assert paid.status_code == 200, paid.text
    assert_order_state(paid.json(), "PAID", reservation_released=False)


@pytest.mark.smoke
def test_order_creation_is_idempotent_without_duplicate_stock_reservation(
    order_client, product_client, merchant_order_no: str, idempotency_key: str
) -> None:
    stock_before = product_client.available_stock("SKU-001")
    first = order_client.create(
        merchant_order_no=merchant_order_no,
        sku="SKU-001",
        quantity=2,
        idempotency_key=idempotency_key,
    )
    replay = order_client.create(
        merchant_order_no=merchant_order_no,
        sku="SKU-001",
        quantity=2,
        idempotency_key=idempotency_key,
    )

    assert first.status_code == 201
    assert replay.status_code == 200
    assert replay.headers["Idempotent-Replayed"] == "true"
    assert replay.json()["id"] == first.json()["id"]
    assert product_client.available_stock("SKU-001") == stock_before - 2
