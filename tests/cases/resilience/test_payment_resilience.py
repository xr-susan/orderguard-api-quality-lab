from __future__ import annotations

import pytest

from tests.support.assertions import assert_order_state


@pytest.mark.resilience
def test_provider_503_recovers_after_two_attempts(
    order_client, mock_admin, merchant_order_no: str, idempotency_key: str
) -> None:
    mock_admin.scenario(merchant_order_no, "unavailable", fail_times=2)
    created = order_client.create(
        merchant_order_no=merchant_order_no,
        sku="SKU-001",
        quantity=1,
        idempotency_key=idempotency_key,
    )
    assert created.status_code == 201

    paid = order_client.pay(created.json()["id"], idempotency_key=f"pay-{idempotency_key}")

    assert paid.status_code == 200, paid.text
    assert_order_state(paid.json(), "PAID", reservation_released=False)
    assert len(paid.json()["payment_attempts"]) == 3
    assert mock_admin.history(merchant_order_no)["count"] == 3


@pytest.mark.resilience
def test_provider_outage_releases_reserved_stock(
    order_client, product_client, mock_admin, merchant_order_no: str, idempotency_key: str
) -> None:
    stock_before = product_client.available_stock("SKU-001")
    mock_admin.scenario(merchant_order_no, "unavailable", fail_times=3)
    created = order_client.create(
        merchant_order_no=merchant_order_no,
        sku="SKU-001",
        quantity=1,
        idempotency_key=idempotency_key,
    )
    assert created.status_code == 201
    assert product_client.available_stock("SKU-001") == stock_before - 1

    payment = order_client.pay(created.json()["id"], idempotency_key=f"pay-{idempotency_key}")
    order = order_client.get(created.json()["id"])

    assert payment.status_code == 502
    assert order.status_code == 200
    assert_order_state(order.json(), "PAYMENT_FAILED", reservation_released=True)
    assert product_client.available_stock("SKU-001") == stock_before
    assert mock_admin.history(merchant_order_no)["count"] == 3
