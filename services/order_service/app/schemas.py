"""Public API request and response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TokenRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sku: str
    name: str
    price: str
    currency: str
    available_stock: int


class CreateOrderRequest(BaseModel):
    merchant_order_no: str = Field(
        min_length=3,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$",
    )
    sku: str = Field(min_length=1, max_length=64)
    quantity: int = Field(ge=1, le=100)


class PaymentAttemptResponse(BaseModel):
    attempt_number: int
    outcome: str
    status_code: int | None
    retryable: bool
    elapsed_ms: int
    error_type: str | None
    created_at: datetime


class OrderResponse(BaseModel):
    id: str
    merchant_order_no: str
    sku: str
    quantity: int
    unit_price: str
    amount: str
    currency: str
    status: Literal["CREATED", "PAYING", "PAID", "PAYMENT_FAILED"]
    payment_id: str | None
    reservation_released: bool
    created_at: datetime
    updated_at: datetime
    payment_attempts: list[PaymentAttemptResponse] = Field(default_factory=list)


class PaymentCallback(BaseModel):
    merchant_order_no: str = Field(min_length=3, max_length=64)
    payment_id: str = Field(min_length=1, max_length=128)
    status: str = Field(min_length=1, max_length=32)

    @field_validator("status")
    @classmethod
    def normalize_status(cls, value: str) -> str:
        return value.strip().upper()


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["order-service"] = "order-service"
