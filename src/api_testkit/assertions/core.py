"""Readable response and JSON assertions with precise failure paths."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import timedelta
from typing import Any, Protocol

from api_testkit.data.models import ExpectedSpec


class ResponseLike(Protocol):
    """Small structural interface implemented by HTTPX and common test doubles."""

    status_code: int
    headers: Mapping[str, str]

    def json(self) -> Any: ...


def _preview(value: Any, *, limit: int = 500) -> str:
    try:
        rendered = json.dumps(value, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        rendered = repr(value)
    if len(rendered) <= limit:
        return rendered
    return f"{rendered[:limit]}...<truncated>"


def _response_text(response: Any) -> str:
    try:
        text = response.text
    except (AttributeError, RuntimeError):
        return "<unavailable>"
    return _preview(text)


def _json_value(actual_or_response: Any) -> Any:
    json_method = getattr(actual_or_response, "json", None)
    if not callable(json_method):
        return actual_or_response
    try:
        return json_method()
    except (ValueError, TypeError) as exc:
        raise AssertionError(
            f"response body is not valid JSON; body={_response_text(actual_or_response)}"
        ) from exc


def _join_path(path: str, key: str | int) -> str:
    if isinstance(key, int):
        return f"{path}[{key}]"
    if key.isidentifier():
        return f"{path}.{key}"
    return f"{path}[{json.dumps(key, ensure_ascii=False)}]"


def _first_exact_difference(actual: Any, expected: Any, path: str = "$") -> str | None:
    if isinstance(expected, Mapping):
        if not isinstance(actual, Mapping):
            return f"{path}: expected object, got {type(actual).__name__} ({_preview(actual)})"
        missing = [key for key in expected if key not in actual]
        extra = [key for key in actual if key not in expected]
        if missing or extra:
            return f"{path}: object keys differ; missing={missing}; extra={extra}"
        for key, expected_value in expected.items():
            difference = _first_exact_difference(
                actual[key], expected_value, _join_path(path, str(key))
            )
            if difference:
                return difference
        return None

    if isinstance(expected, list):
        if not isinstance(actual, list):
            return f"{path}: expected array, got {type(actual).__name__} ({_preview(actual)})"
        if len(actual) != len(expected):
            return f"{path}: array length differs; expected={len(expected)}; actual={len(actual)}"
        for index, expected_value in enumerate(expected):
            difference = _first_exact_difference(
                actual[index], expected_value, _join_path(path, index)
            )
            if difference:
                return difference
        return None

    if isinstance(expected, bool) != isinstance(actual, bool):
        return f"{path}: expected={_preview(expected)}; actual={_preview(actual)}"
    if actual != expected:
        return f"{path}: expected={_preview(expected)}; actual={_preview(actual)}"
    return None


def _first_subset_difference(actual: Any, expected: Any, path: str = "$") -> str | None:
    if isinstance(expected, Mapping):
        if not isinstance(actual, Mapping):
            return f"{path}: expected an object containing {_preview(expected)}"
        for key, expected_value in expected.items():
            if key not in actual:
                return f"{_join_path(path, str(key))}: key is missing"
            difference = _first_subset_difference(
                actual[key], expected_value, _join_path(path, str(key))
            )
            if difference:
                return difference
        return None

    if isinstance(expected, list):
        if not isinstance(actual, list):
            return f"{path}: expected an array containing {_preview(expected)}"
        if len(actual) < len(expected):
            return (
                f"{path}: array is shorter than expected subset; "
                f"minimum={len(expected)}; actual={len(actual)}"
            )
        for index, expected_value in enumerate(expected):
            difference = _first_subset_difference(
                actual[index], expected_value, _join_path(path, index)
            )
            if difference:
                return difference
        return None

    if isinstance(expected, bool) != isinstance(actual, bool) or actual != expected:
        return f"{path}: expected={_preview(expected)}; actual={_preview(actual)}"
    return None


def assert_status_code(response: Any, expected: int) -> None:
    """Assert a response status while retaining a useful body preview."""

    actual = getattr(response, "status_code", None)
    if actual != expected:
        raise AssertionError(
            f"status code mismatch: expected={expected}; actual={actual}; "
            f"body={_response_text(response)}"
        )


def assert_headers(response: Any, expected: Mapping[str, str]) -> None:
    """Assert an expected case-insensitive subset of response headers."""

    raw_headers = getattr(response, "headers", None)
    if not isinstance(raw_headers, Mapping):
        raise AssertionError("response does not expose a headers mapping")
    actual = {str(name).lower(): str(value) for name, value in raw_headers.items()}
    for name, expected_value in expected.items():
        normalized = name.lower()
        if normalized not in actual:
            raise AssertionError(
                f"response header is missing: {name!r}; available={sorted(actual)}"
            )
        if actual[normalized] != str(expected_value):
            raise AssertionError(
                f"response header mismatch for {name!r}: "
                f"expected={expected_value!r}; actual={actual[normalized]!r}"
            )


def assert_json_equal(actual_or_response: Any, expected: Any) -> None:
    """Assert exact JSON equality and report the first differing JSON path."""

    actual = _json_value(actual_or_response)
    difference = _first_exact_difference(actual, expected)
    if difference:
        raise AssertionError(f"JSON mismatch at {difference}")


def assert_json_contains(actual_or_response: Any, expected_subset: Any) -> None:
    """Assert a recursive structural subset.

    Object keys may be omitted from the expected value.  Expected arrays match
    by index and may be a prefix of the actual array, keeping semantics stable
    and predictable for data-driven cases.
    """

    actual = _json_value(actual_or_response)
    difference = _first_subset_difference(actual, expected_subset)
    if difference:
        raise AssertionError(f"JSON subset mismatch at {difference}")


def _parse_json_path(path: str) -> list[str | int]:
    source = path.strip()
    if not source:
        raise ValueError("JSON path must not be blank")
    index = 0
    if source.startswith("$"):
        index = 1
    tokens: list[str | int] = []

    while index < len(source):
        if source[index] == ".":
            index += 1
            if index == len(source):
                raise ValueError(f"JSON path may not end with '.': {path!r}")
        if source[index] == "[":
            closing = source.find("]", index + 1)
            if closing == -1:
                raise ValueError(f"unclosed '[' in JSON path: {path!r}")
            content = source[index + 1 : closing].strip()
            if not content:
                raise ValueError(f"empty bracket selector in JSON path: {path!r}")
            if content[0] in {"'", '"'}:
                quote = content[0]
                if len(content) < 2 or content[-1] != quote:
                    raise ValueError(f"unclosed quoted key in JSON path: {path!r}")
                key = content[1:-1]
                key = key.replace(f"\\{quote}", quote).replace("\\\\", "\\")
                tokens.append(key)
            else:
                try:
                    array_index = int(content)
                except ValueError:
                    tokens.append(content)
                else:
                    if array_index < 0:
                        raise ValueError(f"negative array indexes are not supported: {path!r}")
                    tokens.append(array_index)
            index = closing + 1
            continue

        end = index
        while end < len(source) and source[end] not in ".[":
            end += 1
        key = source[index:end]
        if not key:
            raise ValueError(f"invalid JSON path syntax: {path!r}")
        tokens.append(key)
        index = end
    return tokens


def json_path_value(actual_or_response: Any, path: str) -> Any:
    """Resolve a small, deterministic JSONPath subset.

    Supported examples: ``$.order.id``, ``items[0].sku`` and
    ``$['keys.with.dots']``.  Wildcards and filters are intentionally excluded
    because they make scalar case expectations ambiguous.
    """

    current = _json_value(actual_or_response)
    traversed = "$"
    try:
        tokens = _parse_json_path(path)
    except ValueError as exc:
        raise AssertionError(str(exc)) from exc

    for token in tokens:
        location = _join_path(traversed, token)
        if isinstance(token, int):
            if not isinstance(current, list):
                raise AssertionError(
                    f"JSON path {path!r} cannot select index {token} from "
                    f"{type(current).__name__} at {traversed}"
                )
            if token >= len(current):
                raise AssertionError(
                    f"JSON path {path!r} index is out of range at {location}; "
                    f"array_length={len(current)}"
                )
            current = current[token]
        else:
            if not isinstance(current, Mapping):
                raise AssertionError(
                    f"JSON path {path!r} cannot select key {token!r} from "
                    f"{type(current).__name__} at {traversed}"
                )
            if token not in current:
                raise AssertionError(f"JSON path {path!r} is missing key at {location}")
            current = current[token]
        traversed = location
    return current


def assert_json_path(actual_or_response: Any, path: str, expected: Any) -> None:
    actual = json_path_value(actual_or_response, path)
    difference = _first_exact_difference(actual, expected, path)
    if difference:
        raise AssertionError(f"JSON path mismatch at {difference}")


def assert_json_paths(actual_or_response: Any, expected_paths: Mapping[str, Any]) -> None:
    actual = _json_value(actual_or_response)
    for path, expected in expected_paths.items():
        assert_json_path(actual, path, expected)


def _elapsed_milliseconds(response_or_ms: Any) -> float:
    if isinstance(response_or_ms, bool):
        raise AssertionError("boolean is not a valid response duration")
    if isinstance(response_or_ms, (int, float)):
        return float(response_or_ms)

    for attribute in ("elapsed_ms", "duration_ms"):
        value = getattr(response_or_ms, attribute, None)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)

    try:
        elapsed = response_or_ms.elapsed
    except (AttributeError, RuntimeError) as exc:
        raise AssertionError("response elapsed time is unavailable") from exc
    if isinstance(elapsed, timedelta):
        return elapsed.total_seconds() * 1000
    total_seconds = getattr(elapsed, "total_seconds", None)
    if callable(total_seconds):
        return float(total_seconds()) * 1000
    raise AssertionError(f"unsupported response elapsed type: {type(elapsed).__name__}")


def assert_response_time(response_or_ms: Any, max_duration_ms: float) -> None:
    """Assert an inclusive response-time budget in milliseconds."""

    if max_duration_ms <= 0:
        raise ValueError("max_duration_ms must be greater than zero")
    actual_ms = _elapsed_milliseconds(response_or_ms)
    if actual_ms > max_duration_ms:
        raise AssertionError(
            f"response time exceeded: budget_ms={max_duration_ms:.3f}; "
            f"actual_ms={actual_ms:.3f}; over_by_ms={actual_ms - max_duration_ms:.3f}"
        )


def assert_response(response: Any, expected: ExpectedSpec) -> None:
    """Apply every expectation configured on an ``ExpectedSpec``."""

    assert_status_code(response, expected.status)
    if expected.headers:
        assert_headers(response, expected.headers)

    configured = expected.model_fields_set
    if "json_body" in configured:
        assert_json_equal(response, expected.json_body)
    if "json_contains" in configured:
        assert_json_contains(response, expected.json_contains)
    if expected.json_paths:
        assert_json_paths(response, expected.json_paths)
    if expected.json_schema is not None:
        # Local import avoids a module cycle and keeps the schema dependency at
        # the assertion boundary.
        from .schema import assert_json_schema

        assert_json_schema(response, expected.json_schema)
    if expected.max_duration_ms is not None:
        assert_response_time(response, expected.max_duration_ms)


# Concise compatibility aliases used by some test suites.
assert_status = assert_status_code
assert_json = assert_json_equal
assert_json_subset = assert_json_contains
assert_duration = assert_response_time


__all__ = [
    "ResponseLike",
    "assert_duration",
    "assert_headers",
    "assert_json",
    "assert_json_contains",
    "assert_json_equal",
    "assert_json_path",
    "assert_json_paths",
    "assert_json_subset",
    "assert_response",
    "assert_response_time",
    "assert_status",
    "assert_status_code",
    "json_path_value",
]
