from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class PaymentMockSettings(BaseSettings):
    """Runtime configuration for the payment mock service."""

    model_config = SettingsConfigDict(extra="ignore")

    signing_secret: str = Field(
        default="dev-payment-secret-change-me",
        validation_alias="PAYMENT_SIGNING_SECRET",
    )
    default_timeout_seconds: float = Field(
        default=0.5,
        gt=0,
        validation_alias="PAYMENT_MOCK_TIMEOUT_SECONDS",
    )
    callback_timeout_seconds: float = Field(
        default=2.0,
        gt=0,
        validation_alias="PAYMENT_CALLBACK_TIMEOUT_SECONDS",
    )


@lru_cache
def get_settings() -> PaymentMockSettings:
    return PaymentMockSettings()
