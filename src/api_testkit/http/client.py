"""A thin synchronous HTTPX client with safe retries and diagnostics."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from types import TracebackType
from typing import Any, Self

import httpx
from tenacity import (
    RetryError,
    Retrying,
    retry_if_exception,
    retry_if_result,
    stop_after_attempt,
    stop_before_delay,
)

from api_testkit.config.models import RetrySettings, TimeoutSettings
from api_testkit.errors import ApiTransportError, AuthenticationError
from api_testkit.http.auth import AuthProvider, coerce_auth_provider
from api_testkit.http.hooks import (
    RequestHook,
    RequestObservation,
    ResponseHook,
    ResponseObservation,
)
from api_testkit.http.retry import (
    RetryPolicy,
    RetryWait,
    is_method_retryable,
    is_response_retryable,
    is_transport_retryable,
)
from api_testkit.observability.allure_adapter import AllureAdapter
from api_testkit.observability.context import bind_context, get_context
from api_testkit.observability.redaction import redact, redact_headers, redact_url

logger = logging.getLogger("api_testkit.http")


def _httpx_timeout(value: TimeoutSettings | httpx.Timeout | float | None) -> httpx.Timeout:
    if isinstance(value, httpx.Timeout):
        return value
    if isinstance(value, TimeoutSettings):
        return httpx.Timeout(
            connect=value.connect,
            read=value.read,
            write=value.write,
            pool=value.pool,
        )
    if value is None:
        return httpx.Timeout(10.0, connect=5.0)
    return httpx.Timeout(value)


def _header_value(headers: httpx.Headers, name: str) -> str | None:
    return headers.get(name)


class ApiClient:
    """Compose an :class:`httpx.Client` instead of subclassing it.

    Negative API responses are returned unchanged.  Callers decide whether a
    status is expected; this client only retries explicitly transient outcomes.
    """

    def __init__(
        self,
        base_url: str,
        *,
        auth: str | AuthProvider | Callable[[], str | None] | None = None,
        timeout: TimeoutSettings | httpx.Timeout | float | None = None,
        retry: RetryPolicy | RetrySettings | None = None,
        headers: Mapping[str, str] | None = None,
        transport: httpx.BaseTransport | None = None,
        follow_redirects: bool = False,
        allure: AllureAdapter | None = None,
        request_hooks: Sequence[RequestHook] = (),
        response_hooks: Sequence[ResponseHook] = (),
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not base_url:
            raise ValueError("base_url cannot be empty")
        self._auth = coerce_auth_provider(auth)
        if retry is None:
            self.retry_policy = RetryPolicy()
        elif isinstance(retry, RetryPolicy):
            self.retry_policy = retry
        else:
            self.retry_policy = RetryPolicy.from_settings(retry)
        self._allure = allure or AllureAdapter()
        self._request_hooks = tuple(request_hooks)
        self._response_hooks = tuple(response_hooks)
        self._sleep = sleep
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=_httpx_timeout(timeout),
            headers=dict(headers or {}),
            transport=transport,
            follow_redirects=follow_redirects,
        )

    @property
    def raw_client(self) -> httpx.Client:
        """Expose HTTPX for advanced features without re-wrapping its API."""

        return self._client

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> Self:
        self._client.__enter__()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._client.__exit__(exc_type, exc, traceback)

    def _headers(self, supplied: Mapping[str, str] | None) -> httpx.Headers:
        headers = httpx.Headers(supplied or {})
        if self._auth is not None and "Authorization" not in headers:
            try:
                token = self._auth.get_token()
            except AuthenticationError:
                raise
            except Exception as exc:
                raise AuthenticationError("authentication provider failed") from exc
            if token:
                headers["Authorization"] = f"Bearer {token}"
        context = get_context()
        if context.run_id and "X-Run-ID" not in headers:
            headers["X-Run-ID"] = context.run_id
        if context.case_id and "X-Case-ID" not in headers:
            headers["X-Case-ID"] = context.case_id
        if "X-Request-ID" not in headers:
            headers["X-Request-ID"] = context.request_id or str(uuid.uuid4())
        return headers

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, Any] | Sequence[tuple[str, Any]] | None = None,
        json: Any = None,
        data: Any = None,
        content: str | bytes | None = None,
        files: Any = None,
        timeout: httpx.Timeout | float | None = None,
    ) -> httpx.Response:
        """Send one logical request, retrying only when replay is demonstrably safe."""

        normalised_method = method.upper()
        request_headers = self._headers(headers)
        request_id = _header_value(request_headers, "X-Request-ID") or str(uuid.uuid4())
        attempts = 0

        def send_once() -> httpx.Response:
            nonlocal attempts
            attempts += 1
            with bind_context(request_id=request_id, retry_attempt=attempts):
                started = time.perf_counter()
                request = self._client.build_request(
                    normalised_method,
                    url,
                    headers=request_headers,
                    params=params,
                    json=json,
                    data=data,
                    content=content,
                    files=files,
                    timeout=timeout,
                )
                safe_url = redact_url(str(request.url))
                logger.info(
                    "api request",
                    extra={
                        "http_method": normalised_method,
                        "url": safe_url,
                        "headers": redact_headers(dict(request.headers)),
                        "body": redact(json if json is not None else data),
                    },
                )
                self._allure.attach_json(
                    f"request attempt {attempts}",
                    {
                        "method": normalised_method,
                        "url": safe_url,
                        "headers": dict(request.headers),
                        "body": json if json is not None else data,
                    },
                )
                for hook in self._request_hooks:
                    hook(RequestObservation(request=request, attempt=attempts))
                try:
                    response = self._client.send(request)
                except httpx.TransportError:
                    elapsed = time.perf_counter() - started
                    logger.warning(
                        "api transport failure",
                        extra={
                            "http_method": normalised_method,
                            "url": safe_url,
                            "elapsed_seconds": round(elapsed, 6),
                        },
                    )
                    raise
                elapsed = time.perf_counter() - started
                logger.info(
                    "api response",
                    extra={
                        "http_method": normalised_method,
                        "url": safe_url,
                        "status_code": response.status_code,
                        "elapsed_seconds": round(elapsed, 6),
                        "headers": redact_headers(dict(response.headers)),
                    },
                )
                try:
                    response_body: Any = response.json()
                except (ValueError, UnicodeDecodeError):
                    response_body = response.text
                self._allure.attach_json(
                    f"response attempt {attempts}",
                    {
                        "status": response.status_code,
                        "headers": dict(response.headers),
                        "body": response_body,
                        "elapsed_seconds": elapsed,
                    },
                )
                observation = ResponseObservation(
                    response=response,
                    attempt=attempts,
                    elapsed_seconds=elapsed,
                )
                for hook in self._response_hooks:
                    hook(observation)
                return response

        can_retry = (
            self.retry_policy.enabled
            and self.retry_policy.max_attempts > 1
            and is_method_retryable(normalised_method, request_headers)
        )
        with bind_context(request_id=request_id):
            if not can_retry:
                try:
                    return send_once()
                except httpx.TransportError as exc:
                    raise self._transport_error(exc, normalised_method, url, attempts) from exc

            retrying = Retrying(
                retry=(
                    retry_if_exception(is_transport_retryable)
                    | retry_if_result(self._is_response_retryable)
                ),
                wait=RetryWait(self.retry_policy),
                stop=(
                    stop_after_attempt(self.retry_policy.max_attempts)
                    | stop_before_delay(self.retry_policy.total_budget)
                ),
                sleep=self._sleep,
                reraise=False,
            )
            try:
                return retrying(send_once)
            except RetryError as exc:
                outcome = exc.last_attempt
                if outcome.failed:
                    cause = outcome.exception()
                    assert isinstance(cause, BaseException)
                    raise self._transport_error(cause, normalised_method, url, attempts) from cause
                response = outcome.result()
                assert isinstance(response, httpx.Response)
                return response
            except httpx.TransportError as exc:
                raise self._transport_error(exc, normalised_method, url, attempts) from exc

    @staticmethod
    def _transport_error(
        exc: BaseException, method: str, url: str, attempts: int
    ) -> ApiTransportError:
        return ApiTransportError(
            f"HTTP transport failed: {type(exc).__name__}: {exc}",
            method=method,
            url=redact_url(url),
            attempts=attempts,
        )

    def _is_response_retryable(self, response: httpx.Response) -> bool:
        return is_response_retryable(response, self.retry_policy)

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("GET", url, **kwargs)

    def head(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("HEAD", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("POST", url, **kwargs)


__all__ = ["ApiClient"]
