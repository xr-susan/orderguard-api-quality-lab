"""Pydantic models for the API test framework configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

from pydantic import BeforeValidator, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _normalise_status_codes(value: object) -> object:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


StatusCodes = Annotated[frozenset[int], BeforeValidator(_normalise_status_codes)]


class TimeoutSettings(BaseSettings):
    """Fine-grained HTTPX timeout values in seconds."""

    connect: float = Field(default=5.0, gt=0)
    read: float = Field(default=10.0, gt=0)
    write: float = Field(default=10.0, gt=0)
    pool: float = Field(default=5.0, gt=0)

    model_config = SettingsConfigDict(extra="forbid")


class RetrySettings(BaseSettings):
    """Bounded, idempotency-aware transport retry configuration."""

    enabled: bool = True
    max_attempts: int = Field(default=3, ge=1, le=10)
    total_budget: float = Field(default=10.0, gt=0, le=300)
    base_wait: float = Field(default=0.25, ge=0, le=60)
    max_wait: float = Field(default=3.0, ge=0, le=120)
    jitter: float = Field(default=0.1, ge=0, le=10)
    retry_status_codes: StatusCodes = frozenset({429, 502, 503, 504})

    model_config = SettingsConfigDict(extra="forbid")

    @field_validator("max_wait")
    @classmethod
    def max_wait_cannot_be_less_than_base_wait(cls, value: float, info: object) -> float:
        data = getattr(info, "data", {})
        base_wait = data.get("base_wait", 0.0)
        if value < base_wait:
            raise ValueError("max_wait must be greater than or equal to base_wait")
        return value


class Settings(BaseSettings):
    """Validated runtime settings.

    Values are normally created with :func:`api_testkit.config.load_settings`
    so YAML files and environment variables use the documented precedence.
    """

    env: str = Field(default="local", pattern=r"^[A-Za-z0-9_-]+$")
    base_url: str = "http://127.0.0.1:8000"
    auth_token: SecretStr | None = None
    run_id: str | None = None
    timeout: TimeoutSettings = Field(default_factory=TimeoutSettings)
    retry: RetrySettings = Field(default_factory=RetrySettings)
    log_level: Literal["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"] = "INFO"
    report_dir: Path = Path(".reports/allure-results")

    model_config = SettingsConfigDict(
        env_prefix="ORDERGUARD_",
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="forbid",
    )

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        stripped = value.rstrip("/")
        if not stripped.startswith(("http://", "https://")):
            raise ValueError("base_url must use http:// or https://")
        return stripped

    @field_validator("log_level", mode="before")
    @classmethod
    def normalise_log_level(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value
