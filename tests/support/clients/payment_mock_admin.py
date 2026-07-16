from __future__ import annotations

from typing import Any

import httpx


class PaymentMockAdmin:
    """Thin client for the test-only control plane of the dependency mock."""

    def __init__(self, base_url: str) -> None:
        self._client = httpx.Client(base_url=base_url, timeout=3.0)

    def close(self) -> None:
        self._client.close()

    def health(self, *, timeout: float = 0.3) -> httpx.Response:
        return self._client.get("/health", timeout=timeout)

    def reset(self) -> None:
        response = self._client.post("/__admin/reset")
        assert response.status_code == 204, response.text

    def scenario(self, merchant_order_no: str, behavior: str, **options: Any) -> None:
        response = self._client.post(
            "/__admin/scenarios",
            json={
                "merchant_order_no": merchant_order_no,
                "behavior": behavior,
                **options,
            },
        )
        assert response.status_code == 201, response.text

    def history(self, merchant_order_no: str) -> dict[str, Any]:
        response = self._client.get(f"/__admin/requests/{merchant_order_no}")
        assert response.status_code == 200, response.text
        return response.json()
