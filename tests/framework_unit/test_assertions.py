from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

import pytest

from api_testkit.assertions import (
    assert_headers,
    assert_json_contains,
    assert_json_equal,
    assert_json_path,
    assert_json_paths,
    assert_json_schema,
    assert_response,
    assert_response_time,
    assert_status_code,
    json_path_value,
)
from api_testkit.data import ExpectedSpec
from api_testkit.errors import ContractValidationError


@dataclass
class FakeResponse:
    payload: Any
    status_code: int = 200
    headers: dict[str, str] = field(
        default_factory=lambda: {"Content-Type": "application/json", "X-Request-ID": "r-1"}
    )
    elapsed: timedelta = timedelta(milliseconds=25)

    @property
    def text(self) -> str:
        return json.dumps(self.payload)

    def json(self) -> Any:
        return self.payload


def test_basic_response_assertions_accept_matching_values() -> None:
    response = FakeResponse({"id": "o-1", "status": "CREATED"}, status_code=201)

    assert_status_code(response, 201)
    assert_headers(response, {"content-type": "application/json", "x-request-id": "r-1"})
    assert_json_equal(response, {"id": "o-1", "status": "CREATED"})
    assert_response_time(response, 25)


def test_status_failure_includes_expected_actual_and_body() -> None:
    response = FakeResponse({"code": "OUT_OF_STOCK"}, status_code=409)

    with pytest.raises(AssertionError) as raised:
        assert_status_code(response, 201)

    message = str(raised.value)
    assert "expected=201" in message
    assert "actual=409" in message
    assert "OUT_OF_STOCK" in message


def test_json_exact_failure_reports_first_nested_path() -> None:
    actual = {"order": {"lines": [{"quantity": 2}]}}

    with pytest.raises(AssertionError, match=r"\$\.order\.lines\[0\]\.quantity"):
        assert_json_equal(actual, {"order": {"lines": [{"quantity": 3}]}})


def test_json_subset_supports_nested_objects_and_array_prefixes() -> None:
    actual = {
        "order": {
            "id": "o-1",
            "lines": [
                {"sku": "SKU-1", "quantity": 1},
                {"sku": "SKU-2", "quantity": 2},
            ],
        },
        "trace": "ignored",
    }

    assert_json_contains(actual, {"order": {"lines": [{"sku": "SKU-1"}]}})

    with pytest.raises(AssertionError, match=r"\$\.order\.lines\[0\]\.sku"):
        assert_json_contains(actual, {"order": {"lines": [{"sku": "wrong"}]}})


def test_json_path_supports_dot_index_and_quoted_key_notation() -> None:
    actual = {
        "order": {"lines": [{"sku": "SKU-1"}]},
        "key.with.dot": {"value": None},
    }

    assert_json_path(actual, "$.order.lines[0].sku", "SKU-1")
    assert json_path_value(actual, "$['key.with.dot'].value") is None
    assert_json_paths(actual, {"order.lines[0].sku": "SKU-1", "$['key.with.dot'].value": None})


def test_json_path_distinguishes_missing_key_from_null() -> None:
    actual = {"present": None}

    assert_json_path(actual, "$.present", None)
    with pytest.raises(AssertionError, match="missing key"):
        assert_json_path(actual, "$.missing", None)


def test_response_time_failure_reports_budget_and_overage() -> None:
    with pytest.raises(AssertionError) as raised:
        assert_response_time(FakeResponse({}, elapsed=timedelta(milliseconds=125)), 100)

    message = str(raised.value)
    assert "budget_ms=100.000" in message
    assert "actual_ms=125.000" in message
    assert "over_by_ms=25.000" in message


def test_json_schema_failure_uses_framework_contract_error() -> None:
    pytest.importorskip("jsonschema")
    schema = {
        "type": "object",
        "required": ["id", "quantity"],
        "properties": {
            "id": {"type": "string"},
            "quantity": {"type": "integer", "minimum": 1},
        },
    }

    with pytest.raises(ContractValidationError) as raised:
        assert_json_schema({"id": 123, "quantity": 0}, schema)

    message = str(raised.value)
    assert "JSON Schema validation failed" in message
    assert "$.id" in message
    assert "$.quantity" in message


def test_composite_response_assertion_applies_all_configured_checks() -> None:
    pytest.importorskip("jsonschema")
    response = FakeResponse({"id": "o-1", "status": "CREATED", "quantity": 1}, status_code=201)
    expected = ExpectedSpec(
        status=201,
        headers={"content-type": "application/json"},
        json_contains={"status": "CREATED"},
        json_paths={"$.quantity": 1},
        schema={
            "type": "object",
            "required": ["id"],
            "properties": {"id": {"type": "string"}},
        },
        max_duration_ms=30,
    )

    assert_response(response, expected)


def test_composite_assertion_can_expect_json_null() -> None:
    response = FakeResponse(None)
    expected = ExpectedSpec(json=None)

    assert "json_body" in expected.model_fields_set
    assert_response(response, expected)
