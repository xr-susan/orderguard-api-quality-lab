from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field, HttpUrl, field_validator


class Behavior(StrEnum):
    SUCCESS = "success"
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    UNAVAILABLE = "unavailable"
    DELAYED_CALLBACK = "delayed_callback"
    DUPLICATE_CALLBACK = "duplicate_callback"
    INVALID_SIGNATURE = "invalid_signature"


class ScenarioCreate(BaseModel):
    merchant_order_no: str = Field(min_length=1, max_length=80)
    behavior: Behavior = Behavior.SUCCESS
    fail_times: int | None = Field(default=None, ge=1, le=20)
    delay_seconds: float = Field(default=0.2, ge=0, le=10)
    retry_after_seconds: float = Field(default=0.1, ge=0, le=60)
    callback_delay_seconds: float = Field(default=0.05, ge=0, le=10)

    @field_validator("merchant_order_no")
    @classmethod
    def strip_order_number(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("merchant_order_no cannot be blank")
        return value


class PaymentRequest(BaseModel):
    merchant_order_no: str = Field(min_length=1, max_length=80)
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    currency: str = Field(default="CNY", pattern=r"^[A-Z]{3}$")
    callback_url: HttpUrl


class PaymentResponse(BaseModel):
    payment_id: str
    merchant_order_no: str
    status: str = "succeeded"


class CallbackPayload(BaseModel):
    merchant_order_no: str
    payment_id: str
    status: str


class RecordedRequest(BaseModel):
    attempt: int
    idempotency_key: str
    request: PaymentRequest


class RequestHistory(BaseModel):
    merchant_order_no: str
    count: int
    requests: list[RecordedRequest]
