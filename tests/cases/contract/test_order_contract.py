from __future__ import annotations

import pytest

pytest.importorskip("jsonschema", reason="jsonschema is required for contract validation")

from api_testkit.assertions.schema import assert_json_schema

ORDER_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": [
        "id",
        "merchant_order_no",
        "sku",
        "quantity",
        "amount",
        "currency",
        "status",
        "payment_attempts",
    ],
    "properties": {
        "id": {"type": "string", "minLength": 1},
        "merchant_order_no": {"type": "string", "minLength": 3},
        "sku": {"type": "string"},
        "quantity": {"type": "integer", "minimum": 1},
        "amount": {"type": "string", "pattern": "^[0-9]+\\.[0-9]{2}$"},
        "currency": {"const": "USD"},
        "status": {"enum": ["CREATED", "PAYING", "PAID", "PAYMENT_FAILED"]},
        "payment_attempts": {"type": "array"},
    },
}


@pytest.mark.contract
def test_created_order_matches_independent_contract(
    order_client, merchant_order_no: str, idempotency_key: str
) -> None:
    response = order_client.create(
        merchant_order_no=merchant_order_no,
        sku="SKU-001",
        quantity=1,
        idempotency_key=idempotency_key,
    )

    assert response.status_code == 201
    assert_json_schema(response, ORDER_SCHEMA)
