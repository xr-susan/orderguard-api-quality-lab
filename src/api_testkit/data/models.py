"""Typed models shared by every data-driven case loader."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    field_validator,
    model_validator,
)

# Re-exported deliberately: the loaders import CaseDataError from this module.
# The `as` form marks it as an explicit re-export so mypy's
# no_implicit_reexport (part of --strict) accepts the downstream imports.
from api_testkit.errors import CaseDataError as CaseDataError

# A descriptive compatibility name for callers that prefer loader terminology.
DataLoadError = CaseDataError


class CaseSource(BaseModel):
    """Location of a case in its source document."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    file: str = Field(min_length=1)
    sheet: str | None = None
    row: int | None = Field(default=None, ge=1)


class RequestSpec(BaseModel):
    """Serializable HTTP request definition."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    method: str
    path: str
    headers: dict[str, str] = Field(default_factory=dict)
    query: dict[str, JsonValue] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("query", "params"),
    )
    json_body: JsonValue | None = Field(
        default=None,
        validation_alias=AliasChoices("json", "body", "payload"),
        serialization_alias="json",
    )
    timeout_seconds: float | None = Field(default=None, gt=0)

    @field_validator("method", mode="before")
    @classmethod
    def normalize_method(cls, value: Any) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("method must be a non-empty string")
        method = value.strip().upper()
        if not method.isalpha():
            raise ValueError("method may contain letters only")
        return method

    @field_validator("path")
    @classmethod
    def path_must_not_be_blank(cls, value: str) -> str:
        path = value.strip()
        if not path:
            raise ValueError("path must not be blank")
        return path

    @field_validator("headers")
    @classmethod
    def header_names_must_not_be_blank(cls, value: dict[str, str]) -> dict[str, str]:
        if any(not name.strip() for name in value):
            raise ValueError("header names must not be blank")
        return value


class ExpectedSpec(BaseModel):
    """Expected response properties for a data-driven test."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    status: int = Field(
        default=200,
        ge=100,
        le=599,
        validation_alias=AliasChoices("status", "status_code"),
    )
    headers: dict[str, str] = Field(default_factory=dict)
    json_body: JsonValue | None = Field(
        default=None,
        validation_alias=AliasChoices("json", "json_equals", "body"),
        serialization_alias="json",
    )
    json_contains: JsonValue | None = Field(
        default=None,
        validation_alias=AliasChoices("json_contains", "contains"),
    )
    json_paths: dict[str, JsonValue] = Field(default_factory=dict)
    json_schema: JsonValue | None = Field(
        default=None,
        validation_alias=AliasChoices("schema", "json_schema"),
        serialization_alias="schema",
    )
    max_duration_ms: float | None = Field(
        default=None,
        gt=0,
        validation_alias=AliasChoices("max_duration_ms", "duration_ms", "response_time_ms"),
    )

    @field_validator("headers")
    @classmethod
    def expected_header_names_must_not_be_blank(cls, value: dict[str, str]) -> dict[str, str]:
        if any(not name.strip() for name in value):
            raise ValueError("expected header names must not be blank")
        return value

    @field_validator("json_paths")
    @classmethod
    def json_paths_must_not_be_blank(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        if any(not path.strip() for path in value):
            raise ValueError("JSON paths must not be blank")
        return value


class CaseSpec(BaseModel):
    """Canonical representation produced by all supported case formats."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    id: str
    name: str
    markers: tuple[str, ...] = Field(
        default_factory=tuple,
        validation_alias=AliasChoices("markers", "tags"),
    )
    request: RequestSpec
    expected: ExpectedSpec = Field(default_factory=ExpectedSpec)
    source: CaseSource | None = None

    @model_validator(mode="before")
    @classmethod
    def default_name_to_id(cls, value: Any) -> Any:
        if isinstance(value, Mapping):
            copied = dict(value)
            if copied.get("name") is None and copied.get("id") is not None:
                copied["name"] = copied["id"]
            return copied
        return value

    @field_validator("id", "name", mode="before")
    @classmethod
    def identifiers_must_not_be_blank(cls, value: Any) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("must be a non-empty string")
        return value.strip()

    @field_validator("markers", mode="after")
    @classmethod
    def normalize_markers(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(marker.strip() for marker in value)
        if any(not marker for marker in normalized):
            raise ValueError("markers must not contain blank values")
        if len(set(normalized)) != len(normalized):
            raise ValueError("markers must be unique")
        return normalized
