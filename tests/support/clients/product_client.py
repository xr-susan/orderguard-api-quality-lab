from __future__ import annotations

from typing import Any

from api_testkit.http import ApiClient


class ProductClient:
    def __init__(self, client: ApiClient) -> None:
        self._client = client

    def list(self) -> list[dict[str, Any]]:
        response = self._client.get("/products")
        assert response.status_code == 200, response.text
        payload = response.json()
        assert isinstance(payload, list)
        return payload

    def available_stock(self, sku: str) -> int:
        for product in self.list():
            if product["sku"] == sku:
                return int(product["available_stock"])
        raise AssertionError(f"seed product not found: {sku}")
