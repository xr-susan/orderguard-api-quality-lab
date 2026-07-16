from __future__ import annotations

import os
from uuid import uuid4

import httpx
import pytest

from api_testkit.config import load_settings
from api_testkit.http import ApiClient, RetryPolicy
from api_testkit.observability.context import bind_context
from tests.support.clients import AuthClient, OrderClient, PaymentMockAdmin, ProductClient
from tests.support.environment import TestEnvironment


def _require_services() -> bool:
    return os.getenv("REQUIRE_DEMO_SERVICES", "").lower() in {"1", "true", "yes"}


@pytest.fixture(scope="session")
def environment() -> TestEnvironment:
    return TestEnvironment.from_settings(load_settings())


@pytest.fixture(scope="session")
def raw_api_client(environment: TestEnvironment) -> ApiClient:
    # Test cases must observe the API's first response.  Individual retry
    # behaviour belongs in dedicated resilience tests, not the test runner.
    client = ApiClient(environment.base_url, retry=RetryPolicy(max_attempts=1))
    yield client
    client.close()


@pytest.fixture(scope="session")
def raw_mock_admin(environment: TestEnvironment) -> PaymentMockAdmin:
    client = PaymentMockAdmin(environment.payment_mock_admin_url)
    yield client
    client.close()


@pytest.fixture
def services_ready(raw_api_client: ApiClient, raw_mock_admin: PaymentMockAdmin) -> None:
    try:
        order_health = raw_api_client.raw_client.get("/health", timeout=0.3)
        mock_health = raw_mock_admin.health()
    except httpx.HTTPError as exc:
        if _require_services():
            pytest.fail(f"required demo services are unavailable: {exc}")
        pytest.skip("demo services are not running; use Docker Compose or start both Uvicorn apps")
    if order_health.status_code != 200 or mock_health.status_code != 200:
        message = (
            "service health failed: "
            f"order={order_health.status_code}, mock={mock_health.status_code}"
        )
        if _require_services():
            pytest.fail(message)
        pytest.skip(message)


@pytest.fixture(autouse=True)
def isolated_state(
    services_ready: None,
    raw_api_client: ApiClient,
    raw_mock_admin: PaymentMockAdmin,
    request: pytest.FixtureRequest,
) -> None:
    with bind_context(run_id="local", case_id=request.node.name):
        raw_mock_admin.reset()
        response = raw_api_client.post("/__test__/reset")
        assert response.status_code == 200, response.text
        yield


@pytest.fixture
def api_client(raw_api_client: ApiClient) -> ApiClient:
    return raw_api_client


@pytest.fixture
def auth_token(api_client: ApiClient, environment: TestEnvironment) -> str:
    return AuthClient(api_client).login(environment.username, environment.password)


@pytest.fixture
def order_client(api_client: ApiClient, auth_token: str) -> OrderClient:
    return OrderClient(api_client, auth_token)


@pytest.fixture
def product_client(api_client: ApiClient) -> ProductClient:
    return ProductClient(api_client)


@pytest.fixture
def mock_admin(raw_mock_admin: PaymentMockAdmin) -> PaymentMockAdmin:
    return raw_mock_admin


@pytest.fixture
def merchant_order_no() -> str:
    return f"ORD-{uuid4().hex[:20]}"


@pytest.fixture
def idempotency_key() -> str:
    return f"idem-{uuid4().hex}"
