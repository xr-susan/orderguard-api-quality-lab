from __future__ import annotations

from typing import Any

from api_testkit.http import ApiClient


class OrderClient:
    def __init__(self, client: ApiClient, bearer_token: str) -> None:
        self._client = client
        self._headers = {"Authorization": f"Bearer {bearer_token}"}

    def create(
        self,
        *,
        merchant_order_no: str,
        sku: str,
        quantity: int,
        idempotency_key: str,
    ) -> Any:
        return self._client.post(
            "/orders",
            headers={**self._headers, "Idempotency-Key": idempotency_key},
            json={
                "merchant_order_no": merchant_order_no,
                "sku": sku,
                "quantity": quantity,
            },
        )

    def pay(self, order_id: str, *, idempotency_key: str) -> Any:
        return self._client.post(
            f"/orders/{order_id}/pay",
            headers={**self._headers, "Idempotency-Key": idempotency_key},
        )

    def get(self, order_id: str) -> Any:
        return self._client.get(f"/orders/{order_id}", headers=self._headers)
