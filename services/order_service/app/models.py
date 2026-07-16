"""SQLAlchemy persistence models."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sku: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    stock: Mapped[int] = mapped_column(Integer, nullable=False)


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    merchant_order_no: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    owner_username: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    sku: Mapped[str] = mapped_column(String(64), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    create_idempotency_key: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False, index=True
    )
    create_request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payment_idempotency_key: Mapped[str | None] = mapped_column(
        String(128), unique=True, nullable=True, index=True
    )
    payment_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reservation_released: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    payment_attempts: Mapped[list[PaymentAttempt]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="PaymentAttempt.attempt_number",
    )


class PaymentAttempt(Base):
    __tablename__ = "payment_attempts"
    __table_args__ = (
        UniqueConstraint("order_id", "attempt_number", name="uq_attempt_order_number"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retryable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    elapsed_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    error_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    order: Mapped[Order] = relationship(back_populates="payment_attempts")
