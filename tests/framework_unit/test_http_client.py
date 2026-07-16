from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import httpx
import pytest

from api_testkit.config import TimeoutSettings
from api_testkit.errors import ApiTransportError
from api_testkit.http import ApiClient, RetryPolicy, is_method_retryable, parse_retry_after
from api_testkit.http.hooks import RequestObservation, ResponseObservation
from api_testkit.observability import bind_context


def make_client(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    retry: RetryPolicy | None = None,
    auth: str | None = None,
    sleep: Callable[[float], None] = lambda _: None,
    **kwargs: object,
) -> ApiClient:
    return ApiClient(
        "https://orders.test/api",
        transport=httpx.MockTransport(handler),
        retry=retry or RetryPolicy(base_wait=0, max_wait=0, jitter=0),
        auth=auth,
        sleep=sleep,
        **kwargs,
    )


def test_request_injects_auth_and_correlation_headers() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"ok": True})

    with (
        bind_context(run_id="run-1", case_id="case-1", request_id="request-1"),
        make_client(handler, auth="access-token") as client,
    ):
        response = client.get("/orders/1")

    assert response.json() == {"ok": True}
    assert seen[0].url == httpx.URL("https://orders.test/api/orders/1")
    assert seen[0].headers["Authorization"] == "Bearer access-token"
    assert seen[0].headers["X-Run-ID"] == "run-1"
    assert seen[0].headers["X-Case-ID"] == "case-1"
    assert seen[0].headers["X-Request-ID"] == "request-1"


def test_caller_headers_override_auth_and_request_id() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(204)

    with make_client(handler, auth="default-token") as client:
        client.get(
            "/health",
            headers={"Authorization": "Custom credential", "X-Request-ID": "chosen"},
        )

    assert seen[0].headers["Authorization"] == "Custom credential"
    assert seen[0].headers["X-Request-ID"] == "chosen"


def test_negative_response_is_returned_without_raise_for_status() -> None:
    with make_client(lambda _: httpx.Response(409, json={"code": "duplicate"})) as client:
        response = client.post("/orders")

    assert response.status_code == 409
    assert response.json()["code"] == "duplicate"


def test_get_retries_transient_response_and_keeps_request_id() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.headers["X-Request-ID"])
        status = 503 if len(calls) < 3 else 200
        return httpx.Response(status, json={"attempt": len(calls)})

    with make_client(handler) as client:
        response = client.get("/orders/1")

    assert response.status_code == 200
    assert len(calls) == 3
    assert len(set(calls)) == 1


def test_retry_after_is_preferred_over_exponential_wait() -> None:
    waits: list[float] = []
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "2"})
        return httpx.Response(200)

    policy = RetryPolicy(base_wait=0.5, max_wait=1, jitter=0, total_budget=10)
    with make_client(handler, retry=policy, sleep=waits.append) as client:
        response = client.get("/products")

    assert response.status_code == 200
    assert waits == [2.0]


def test_get_retries_connection_error_then_succeeds() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ConnectError("connection refused", request=request)
        return httpx.Response(200)

    with make_client(handler) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert calls == 2


def test_non_idempotent_post_is_never_replayed() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503)

    with make_client(handler) as client:
        response = client.post("/orders")

    assert response.status_code == 503
    assert calls == 1


def test_post_with_idempotency_key_can_retry() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503 if calls == 1 else 201)

    with make_client(handler) as client:
        response = client.post(
            "/orders", headers={"idempotency-key": "case-123"}, json={"sku": "A"}
        )

    assert response.status_code == 201
    assert calls == 2


def test_non_retryable_4xx_is_not_replayed() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(400)

    with make_client(handler) as client:
        response = client.get("/orders/invalid")

    assert response.status_code == 400
    assert calls == 1


def test_exhausted_status_retry_returns_last_response() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, json={"attempt": calls})

    policy = RetryPolicy(max_attempts=2, base_wait=0, max_wait=0, jitter=0)
    with make_client(handler, retry=policy) as client:
        response = client.get("/orders/1")

    assert response.status_code == 503
    assert response.json() == {"attempt": 2}


def test_exhausted_transport_retry_is_wrapped_with_cause() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("slow dependency", request=request)

    policy = RetryPolicy(max_attempts=2, base_wait=0, max_wait=0, jitter=0)
    with (
        make_client(handler, retry=policy) as client,
        pytest.raises(ApiTransportError, match="attempts=2") as captured,
    ):
        client.get("/orders/1")

    assert calls == 2
    assert isinstance(captured.value.__cause__, httpx.ReadTimeout)


def test_transport_error_on_unsafe_method_is_wrapped_without_retry() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("offline", request=request)

    with (
        make_client(handler) as client,
        pytest.raises(ApiTransportError, match="attempts=1"),
    ):
        client.post("/orders")

    assert calls == 1


def test_request_and_response_hooks_receive_attempt_metadata() -> None:
    requests: list[RequestObservation] = []
    responses: list[ResponseObservation] = []
    with make_client(
        lambda _: httpx.Response(200),
        request_hooks=[requests.append],
        response_hooks=[responses.append],
    ) as client:
        client.get("/health")

    assert requests[0].attempt == 1
    assert responses[0].attempt == 1
    assert responses[0].elapsed_seconds >= 0


def test_fine_grained_timeout_is_applied() -> None:
    timeout = TimeoutSettings(connect=1, read=2, write=3, pool=4)
    with make_client(lambda _: httpx.Response(200), timeout=timeout) as client:
        configured = client.raw_client.timeout

    assert configured.connect == 1
    assert configured.read == 2
    assert configured.write == 3
    assert configured.pool == 4


@pytest.mark.parametrize(
    ("method", "headers", "expected"),
    [
        ("GET", {}, True),
        ("head", {}, True),
        ("POST", {}, False),
        ("POST", {"Idempotency-Key": "abc"}, True),
        ("PATCH", {"Idempotency-Key": "abc"}, False),
    ],
)
def test_retry_method_safety_rule(method: str, headers: dict[str, str], expected: bool) -> None:
    assert is_method_retryable(method, headers) is expected


def test_parse_retry_after_supports_seconds_and_http_dates() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    future = format_datetime(now + timedelta(seconds=5), usegmt=True)

    assert parse_retry_after("2.5", now=now) == 2.5
    assert parse_retry_after(future, now=now) == 5
    assert parse_retry_after("not-a-date", now=now) is None
    assert parse_retry_after("-3", now=now) == 0
