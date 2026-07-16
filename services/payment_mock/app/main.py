from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Annotated

import httpx
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Response, status
from fastapi.responses import JSONResponse

from .config import get_settings
from .models import (
    Behavior,
    CallbackPayload,
    PaymentRequest,
    PaymentResponse,
    RequestHistory,
    ScenarioCreate,
)
from .store import store

app = FastAPI(
    title="OrderGuard Payment Mock",
    version="1.0.0",
    description="Programmable payment dependency with a test-only control plane.",
)


def _canonical_json(payload: dict[str, str]) -> bytes:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _signature(body: bytes, *, invalid: bool = False) -> str:
    secret = get_settings().signing_secret.encode("utf-8")
    signature = hmac.new(secret, body, hashlib.sha256).hexdigest()
    return f"invalid-{signature}" if invalid else signature


def _send_callback(
    callback_url: str,
    payload: CallbackPayload,
    *,
    delay_seconds: float,
    invalid_signature: bool,
    repeats: int,
) -> None:
    if delay_seconds:
        time.sleep(delay_seconds)
    payload_dict = payload.model_dump(mode="json")
    body = _canonical_json(payload_dict)
    headers = {
        "Content-Type": "application/json",
        "X-Payment-Signature": _signature(body, invalid=invalid_signature),
    }
    with httpx.Client(timeout=get_settings().callback_timeout_seconds) as client:
        for _ in range(repeats):
            try:
                client.post(callback_url, content=body, headers=headers)
            except httpx.HTTPError:
                # A dependency mock must not turn callback delivery failures into
                # failures of the original payment response.
                continue


def _effective_behavior(config: ScenarioCreate, attempt: int) -> Behavior:
    transient = {Behavior.TIMEOUT, Behavior.RATE_LIMIT, Behavior.UNAVAILABLE}
    if (
        config.behavior in transient
        and config.fail_times is not None
        and attempt > config.fail_times
    ):
        return Behavior.SUCCESS
    return config.behavior


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "payment-mock"}


@app.post("/payments", response_model=PaymentResponse, status_code=status.HTTP_201_CREATED)
def create_payment(
    request: PaymentRequest,
    background_tasks: BackgroundTasks,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1)],
) -> PaymentResponse | JSONResponse:
    existing = store.get_payment(idempotency_key)
    if existing is not None:
        if existing.request != request:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Idempotency-Key was already used with a different payload",
            )
        # Repeated requests are still observable to tests.
        store.record(request, idempotency_key)
        return existing.response

    config, attempt = store.record(request, idempotency_key)
    behavior = _effective_behavior(config, attempt)

    if behavior == Behavior.RATE_LIMIT:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            headers={"Retry-After": str(config.retry_after_seconds)},
            content={"detail": "payment provider rate limit"},
        )
    if behavior == Behavior.UNAVAILABLE:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": "payment provider unavailable"},
        )
    if behavior == Behavior.TIMEOUT:
        time.sleep(config.delay_seconds or get_settings().default_timeout_seconds)

    payment_id = f"pay_{hashlib.sha256(request.merchant_order_no.encode()).hexdigest()[:16]}"
    response = PaymentResponse(
        payment_id=payment_id,
        merchant_order_no=request.merchant_order_no,
    )
    store.save_payment(idempotency_key, request, response)

    callback_behavior = {
        Behavior.DELAYED_CALLBACK,
        Behavior.DUPLICATE_CALLBACK,
        Behavior.INVALID_SIGNATURE,
    }
    if behavior in callback_behavior:
        payload = CallbackPayload(
            merchant_order_no=request.merchant_order_no,
            payment_id=payment_id,
            status="succeeded",
        )
        background_tasks.add_task(
            _send_callback,
            str(request.callback_url),
            payload,
            delay_seconds=config.callback_delay_seconds,
            invalid_signature=behavior == Behavior.INVALID_SIGNATURE,
            repeats=2 if behavior == Behavior.DUPLICATE_CALLBACK else 1,
        )
    return response


@app.post("/__admin/scenarios", status_code=status.HTTP_201_CREATED)
def configure_scenario(scenario: ScenarioCreate) -> dict[str, str]:
    store.register(scenario)
    return {"merchant_order_no": scenario.merchant_order_no, "status": "configured"}


@app.get("/__admin/requests/{merchant_order_no}", response_model=RequestHistory)
def request_history(merchant_order_no: str) -> RequestHistory:
    requests = store.get_history(merchant_order_no)
    return RequestHistory(
        merchant_order_no=merchant_order_no,
        count=len(requests),
        requests=requests,
    )


@app.delete("/__admin/scenarios/{merchant_order_no}", status_code=status.HTTP_204_NO_CONTENT)
def delete_scenario(merchant_order_no: str) -> Response:
    store.remove(merchant_order_no)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/__admin/reset", status_code=status.HTTP_204_NO_CONTENT)
def reset() -> Response:
    store.reset()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
