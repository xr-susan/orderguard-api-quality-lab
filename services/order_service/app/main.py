"""FastAPI routes for the controllable demo order service."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from contextlib import asynccontextmanager
from typing import Annotated, Any
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, status
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from .auth import DEMO_USERS, CurrentUser, get_current_user, issue_token
from .config import Settings
from .db import Database, get_session
from .models import Order, PaymentAttempt, Product
from .payment_client import AttemptRecord, PaymentClient, PaymentServiceError
from .schemas import (
    CreateOrderRequest,
    HealthResponse,
    OrderResponse,
    PaymentAttemptResponse,
    PaymentCallback,
    ProductResponse,
    TokenRequest,
    TokenResponse,
)

LOGGER = logging.getLogger("order_service")
SUCCESS_PAYMENT_STATUSES = frozenset({"SUCCESS", "SUCCEEDED", "PAID"})
FAILED_PAYMENT_STATUSES = frozenset({"FAILED", "FAILURE", "DECLINED", "CANCELLED"})
IdempotencyKey = Annotated[
    str,
    Header(alias="Idempotency-Key", min_length=1, max_length=128),
]
DbSession = Annotated[Session, Depends(get_session)]
AuthenticatedUser = Annotated[CurrentUser, Depends(get_current_user)]


def create_app(
    settings: Settings | None = None,
    *,
    payment_client: Any | None = None,
) -> FastAPI:
    resolved_settings = settings or Settings()
    database = Database(resolved_settings.database_url)
    resolved_payment_client = payment_client or PaymentClient(resolved_settings)
    owns_payment_client = payment_client is None

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        database.init_schema()
        yield
        if owns_payment_client:
            await resolved_payment_client.aclose()
        database.dispose()

    application = FastAPI(
        title="OrderGuard Demo Order Service",
        version="1.0.0",
        lifespan=lifespan,
    )
    application.state.settings = resolved_settings
    application.state.database = database
    application.state.payment_client = resolved_payment_client

    @application.get("/health", response_model=HealthResponse, tags=["system"])
    def health(session: DbSession) -> HealthResponse:
        session.execute(text("SELECT 1"))
        return HealthResponse()

    @application.post("/auth/token", response_model=TokenResponse, tags=["auth"])
    def token(credentials: TokenRequest) -> TokenResponse:
        expected_password = DEMO_USERS.get(credentials.username)
        if expected_password is None or not hmac.compare_digest(
            expected_password, credentials.password
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "code": "INVALID_CREDENTIALS",
                    "message": "Username or password is invalid",
                },
                headers={"WWW-Authenticate": "Bearer"},
            )
        access_token = issue_token(
            credentials.username,
            resolved_settings.auth_secret,
            resolved_settings.token_ttl_seconds,
        )
        return TokenResponse(
            access_token=access_token,
            expires_in=resolved_settings.token_ttl_seconds,
        )

    @application.get("/products", response_model=list[ProductResponse], tags=["products"])
    def products(session: DbSession) -> list[ProductResponse]:
        records = session.scalars(select(Product).order_by(Product.sku)).all()
        return [
            ProductResponse(
                sku=item.sku,
                name=item.name,
                price=_money(item.price_cents),
                currency=item.currency,
                available_stock=item.stock,
            )
            for item in records
        ]

    @application.post(
        "/orders",
        response_model=OrderResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["orders"],
    )
    def create_order(
        payload: CreateOrderRequest,
        response: Response,
        idempotency_key: IdempotencyKey,
        session: DbSession,
        user: AuthenticatedUser,
    ) -> OrderResponse:
        request_hash = _request_hash(payload.model_dump(), user.username)
        replay = session.scalar(
            select(Order)
            .options(selectinload(Order.payment_attempts))
            .where(Order.create_idempotency_key == idempotency_key)
        )
        if replay is not None:
            if replay.create_request_hash != request_hash:
                raise _conflict(
                    "IDEMPOTENCY_KEY_REUSED",
                    "Idempotency-Key was already used with a different request",
                )
            response.status_code = status.HTTP_200_OK
            response.headers["Idempotent-Replayed"] = "true"
            return _order_response(replay)

        if (
            session.scalar(
                select(Order.id).where(Order.merchant_order_no == payload.merchant_order_no)
            )
            is not None
        ):
            raise _conflict(
                "MERCHANT_ORDER_EXISTS",
                "merchant_order_no already exists",
            )

        product = session.scalar(select(Product).where(Product.sku == payload.sku))
        if product is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "PRODUCT_NOT_FOUND", "message": "Product does not exist"},
            )
        if product.stock < payload.quantity:
            raise _conflict("INSUFFICIENT_STOCK", "Not enough available stock")

        product.stock -= payload.quantity
        order = Order(
            id=str(uuid4()),
            merchant_order_no=payload.merchant_order_no,
            owner_username=user.username,
            sku=product.sku,
            quantity=payload.quantity,
            unit_price_cents=product.price_cents,
            amount_cents=product.price_cents * payload.quantity,
            currency=product.currency,
            status="CREATED",
            create_idempotency_key=idempotency_key,
            create_request_hash=request_hash,
            reservation_released=False,
        )
        session.add(order)
        try:
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            raise _conflict(
                "ORDER_CONFLICT",
                "Order or idempotency key was created concurrently",
            ) from exc
        return _order_response(order)

    @application.post(
        "/orders/{order_id}/pay",
        response_model=OrderResponse,
        tags=["payments"],
    )
    async def pay_order(
        order_id: str,
        response: Response,
        idempotency_key: IdempotencyKey,
        session: DbSession,
        user: AuthenticatedUser,
    ) -> OrderResponse:
        order = _owned_order(session, order_id, user.username)

        if order.payment_idempotency_key is not None:
            if order.payment_idempotency_key != idempotency_key:
                raise _conflict(
                    "PAYMENT_ALREADY_REQUESTED",
                    "A payment was already requested with a different idempotency key",
                )
            response.headers["Idempotent-Replayed"] = "true"
            return _order_response(order)
        reused_key = session.scalar(
            select(Order.id).where(Order.payment_idempotency_key == idempotency_key)
        )
        if reused_key is not None:
            raise _conflict(
                "IDEMPOTENCY_KEY_REUSED",
                "Payment Idempotency-Key is already associated with another order",
            )
        if order.status != "CREATED":
            raise _conflict("INVALID_ORDER_STATE", "Only CREATED orders can be paid")

        order.payment_idempotency_key = idempotency_key
        order.status = "PAYING"
        session.commit()

        try:
            payment_result = await application.state.payment_client.create_payment(
                merchant_order_no=order.merchant_order_no,
                amount=order.amount_cents / 100,
                currency=order.currency,
                callback_url=resolved_settings.payment_callback_url,
                idempotency_key=idempotency_key,
            )
        except PaymentServiceError as exc:
            _persist_attempts(session, order, exc.attempts)
            _mark_payment_failed(session, order)
            session.commit()
            LOGGER.warning(
                "payment_failed order_id=%s code=%s attempts=%d",
                order.id,
                exc.code,
                len(exc.attempts),
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "code": exc.code,
                    "message": str(exc),
                    "attempts": len(exc.attempts),
                    "order_status": order.status,
                },
            ) from exc

        _persist_attempts(session, order, payment_result.attempts)
        order.payment_id = payment_result.payment_id
        if payment_result.status in SUCCESS_PAYMENT_STATUSES:
            order.status = "PAID"
        elif payment_result.status in FAILED_PAYMENT_STATUSES:
            _mark_payment_failed(session, order)
        else:
            order.status = "PAYING"
        session.commit()
        return _order_response(order)

    @application.get(
        "/orders/{order_id}",
        response_model=OrderResponse,
        tags=["orders"],
    )
    def get_order(
        order_id: str,
        session: DbSession,
        user: AuthenticatedUser,
    ) -> OrderResponse:
        return _order_response(_owned_order(session, order_id, user.username))

    @application.post(
        "/payments/callback",
        response_model=OrderResponse,
        tags=["payments"],
    )
    async def payment_callback(
        request: Request,
        session: DbSession,
        payment_signature: Annotated[str | None, Header(alias="X-Payment-Signature")] = None,
    ) -> OrderResponse:
        raw_body = await request.body()
        if not _valid_callback_signature(
            raw_body,
            payment_signature,
            resolved_settings.payment_callback_secret,
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "INVALID_SIGNATURE", "message": "Payment signature is invalid"},
            )
        try:
            callback = PaymentCallback.model_validate_json(raw_body)
        except ValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "INVALID_CALLBACK", "message": "Callback payload is invalid"},
            ) from exc

        order = session.scalar(
            select(Order)
            .options(selectinload(Order.payment_attempts))
            .where(Order.merchant_order_no == callback.merchant_order_no)
        )
        if order is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "ORDER_NOT_FOUND", "message": "Order does not exist"},
            )
        if order.status == "CREATED":
            raise _conflict("PAYMENT_NOT_REQUESTED", "Order has no payment in progress")
        if order.payment_id is not None and order.payment_id != callback.payment_id:
            raise _conflict(
                "PAYMENT_ID_MISMATCH",
                "Callback payment_id does not match the order payment",
            )

        order.payment_id = callback.payment_id
        if callback.status in SUCCESS_PAYMENT_STATUSES:
            if order.status == "PAYMENT_FAILED":
                raise _conflict(
                    "ORDER_ALREADY_FAILED",
                    "A released order cannot transition back to PAID",
                )
            order.status = "PAID"
        elif callback.status in FAILED_PAYMENT_STATUSES:
            if order.status != "PAID":
                _mark_payment_failed(session, order)
        else:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "UNKNOWN_PAYMENT_STATUS", "message": "Unsupported payment status"},
            )
        session.commit()
        return _order_response(order)

    @application.post("/__test__/reset", tags=["test-control"])
    def reset_state() -> dict[str, str]:
        if resolved_settings.is_production:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
        database.reset()
        return {"status": "reset"}

    return application


def _owned_order(session: Session, order_id: str, username: str) -> Order:
    order = session.scalar(
        select(Order)
        .options(selectinload(Order.payment_attempts))
        .where(Order.id == order_id, Order.owner_username == username)
    )
    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "ORDER_NOT_FOUND", "message": "Order does not exist"},
        )
    return order


def _mark_payment_failed(session: Session, order: Order) -> None:
    order.status = "PAYMENT_FAILED"
    if not order.reservation_released:
        product = session.scalar(select(Product).where(Product.sku == order.sku))
        if product is not None:
            product.stock += order.quantity
        order.reservation_released = True


def _persist_attempts(
    session: Session,
    order: Order,
    attempts: tuple[AttemptRecord, ...],
) -> None:
    for attempt in attempts:
        record = PaymentAttempt(
            order_id=order.id,
            attempt_number=attempt.attempt_number,
            outcome=attempt.outcome,
            status_code=attempt.status_code,
            retryable=attempt.retryable,
            elapsed_ms=attempt.elapsed_ms,
            error_type=attempt.error_type,
        )
        session.add(record)
        order.payment_attempts.append(record)


def _order_response(order: Order) -> OrderResponse:
    attempts = [
        PaymentAttemptResponse(
            attempt_number=item.attempt_number,
            outcome=item.outcome,
            status_code=item.status_code,
            retryable=item.retryable,
            elapsed_ms=item.elapsed_ms,
            error_type=item.error_type,
            created_at=item.created_at,
        )
        for item in sorted(order.payment_attempts, key=lambda value: value.attempt_number)
    ]
    return OrderResponse(
        id=order.id,
        merchant_order_no=order.merchant_order_no,
        sku=order.sku,
        quantity=order.quantity,
        unit_price=_money(order.unit_price_cents),
        amount=_money(order.amount_cents),
        currency=order.currency,
        status=order.status,
        payment_id=order.payment_id,
        reservation_released=order.reservation_released,
        created_at=order.created_at,
        updated_at=order.updated_at,
        payment_attempts=attempts,
    )


def _money(cents: int) -> str:
    return f"{cents / 100:.2f}"


def _request_hash(payload: dict[str, Any], username: str) -> str:
    canonical = json.dumps(
        {"owner": username, "payload": payload},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _valid_callback_signature(raw_body: bytes, supplied: str | None, secret: str) -> bool:
    if not supplied:
        return False
    normalized = supplied.removeprefix("sha256=")
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, normalized)


def _conflict(code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": code, "message": message},
    )


app = create_app()
