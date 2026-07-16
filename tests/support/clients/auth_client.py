from __future__ import annotations

from api_testkit.http import ApiClient


class AuthClient:
    def __init__(self, client: ApiClient) -> None:
        self._client = client

    def login(self, username: str, password: str) -> str:
        response = self._client.post(
            "/auth/token", json={"username": username, "password": password}
        )
        assert response.status_code == 200, response.text
        return str(response.json()["access_token"])
