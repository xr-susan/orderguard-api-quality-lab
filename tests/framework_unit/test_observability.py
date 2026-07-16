from __future__ import annotations

import json
from io import StringIO

from api_testkit.observability import (
    REDACTED,
    AllureAdapter,
    bind_context,
    configure_logging,
    get_context,
    redact,
    redact_headers,
    redact_text,
    redact_url,
)


def test_context_is_nested_and_restored() -> None:
    assert get_context().case_id is None
    with bind_context(run_id="run-1", case_id="case-1"):
        assert get_context().run_id == "run-1"
        assert get_context().case_id == "case-1"
        with bind_context(case_id="case-2", retry_attempt=2):
            assert get_context().case_id == "case-2"
            assert get_context().retry_attempt == 2
        assert get_context().case_id == "case-1"
        assert get_context().retry_attempt is None
    assert get_context().run_id is None


def test_recursive_redaction_does_not_mutate_source() -> None:
    source = {
        "user": "alice",
        "password": "very-secret",
        "nested": {"accessToken": "abc", "items": [{"cvv": "123"}]},
    }

    result = redact(source)

    assert result == {
        "user": "alice",
        "password": REDACTED,
        "nested": {"accessToken": REDACTED, "items": [{"cvv": REDACTED}]},
    }
    assert source["password"] == "very-secret"


def test_header_and_url_redaction_retain_diagnostic_values() -> None:
    headers = redact_headers(
        {"Authorization": "Bearer abc", "Cookie": "sid=1", "X-Request-ID": "r-1"}
    )
    url = redact_url("https://example.test/pay?token=abc&order_id=42&signature=sig")

    assert headers["Authorization"] == REDACTED
    assert headers["Cookie"] == REDACTED
    assert headers["X-Request-ID"] == "r-1"
    assert "token=abc" not in url and "signature=sig" not in url
    assert "order_id=42" in url


def test_free_text_redacts_bearer_and_key_value_pairs() -> None:
    value = "Authorization=Bearer abc.def token:xyz password=hunter2"
    redacted = redact_text(value)

    assert "abc.def" not in redacted
    assert "xyz" not in redacted
    assert "hunter2" not in redacted
    assert REDACTED in redacted


def test_json_logger_includes_context_and_redacts_extra_fields() -> None:
    stream = StringIO()
    logger = configure_logging(stream=stream)
    with bind_context(run_id="run-1", case_id="case-1", request_id="req-1", retry_attempt=2):
        logger.info(
            "calling with token=%s",
            "plain-secret",
            extra={
                "headers": {"Authorization": "Bearer header-secret"},
                "status_code": 503,
            },
        )

    payload = json.loads(stream.getvalue())
    assert payload["run_id"] == "run-1"
    assert payload["case_id"] == "case-1"
    assert payload["request_id"] == "req-1"
    assert payload["retry_attempt"] == 2
    assert payload["status_code"] == 503
    rendered = stream.getvalue()
    assert "plain-secret" not in rendered
    assert "header-secret" not in rendered


def test_allure_adapter_is_safe_without_optional_dependency() -> None:
    adapter = AllureAdapter(enabled=True, max_attachment_bytes=32)

    adapter.attach_text("token", "Bearer hidden")
    adapter.attach_json("body", {"password": "hidden"})
    with adapter.step("diagnostic step"):
        pass
