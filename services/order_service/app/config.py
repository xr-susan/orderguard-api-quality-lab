"""Environment-backed configuration for the order service."""

from __future__ import annotations

from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings.

    Explicit validation aliases keep the public environment variable names stable
    without leaking those names throughout the application.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    environment: Literal["development", "test", "production"] = Field(
        default="development",
        validation_alias=AliasChoices("APP_ENV", "ENVIRONMENT"),
    )
    database_url: str = Field(
        default="sqlite:///./orderguard.db",
        validation_alias=AliasChoices("ORDER_DATABASE_URL", "DATABASE_URL"),
    )
    payment_base_url: str = Field(
        default="http://payment-mock:8001",
        validation_alias="PAYMENT_BASE_URL",
    )
    public_base_url: str = Field(
        default="http://order-service:8000",
        validation_alias=AliasChoices("ORDER_PUBLIC_BASE_URL", "PUBLIC_BASE_URL"),
    )
    payment_callback_secret: str = Field(
        default="dev-payment-secret-change-me",
        min_length=16,
        validation_alias=AliasChoices(
            "PAYMENT_CALLBACK_SECRET",
            "PAYMENT_SIGNING_SECRET",
        ),
    )
    auth_secret: str = Field(
        default="local-order-auth-secret-change-me",
        min_length=16,
        validation_alias="AUTH_SECRET",
    )
    token_ttl_seconds: int = Field(
        default=3600,
        ge=60,
        le=86_400,
        validation_alias="TOKEN_TTL_SECONDS",
    )
    payment_timeout_seconds: float = Field(
        default=1.0,
        gt=0,
        le=30,
        validation_alias="PAYMENT_TIMEOUT_SECONDS",
    )
    payment_max_attempts: int = Field(
        default=3,
        ge=1,
        le=3,
        validation_alias="PAYMENT_MAX_ATTEMPTS",
    )
    payment_retry_base_delay_seconds: float = Field(
        default=0.1,
        ge=0,
        le=5,
        validation_alias="PAYMENT_RETRY_BASE_DELAY_SECONDS",
    )
    payment_retry_max_delay_seconds: float = Field(
        default=10.0,
        gt=0,
        le=60,
        validation_alias="PAYMENT_RETRY_MAX_DELAY_SECONDS",
    )

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def payment_callback_url(self) -> str:
        return f"{self.public_base_url.rstrip('/')}/payments/callback"
