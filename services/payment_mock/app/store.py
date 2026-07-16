from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock

from .models import PaymentRequest, PaymentResponse, RecordedRequest, ScenarioCreate


@dataclass
class ScenarioState:
    config: ScenarioCreate
    attempts: int = 0


@dataclass
class IdempotentPayment:
    request: PaymentRequest
    response: PaymentResponse


@dataclass
class ScenarioStore:
    """Thread-safe in-memory control plane for deterministic test scenarios."""

    _scenarios: dict[str, ScenarioState] = field(default_factory=dict)
    _history: dict[str, list[RecordedRequest]] = field(default_factory=dict)
    _payments: dict[str, IdempotentPayment] = field(default_factory=dict)
    _lock: RLock = field(default_factory=RLock)

    def register(self, scenario: ScenarioCreate) -> None:
        with self._lock:
            self._scenarios[scenario.merchant_order_no] = ScenarioState(config=scenario)
            self._history.pop(scenario.merchant_order_no, None)

    def remove(self, merchant_order_no: str) -> bool:
        with self._lock:
            removed = self._scenarios.pop(merchant_order_no, None) is not None
            self._history.pop(merchant_order_no, None)
            stale_keys = [
                key
                for key, value in self._payments.items()
                if value.request.merchant_order_no == merchant_order_no
            ]
            for key in stale_keys:
                self._payments.pop(key, None)
            return removed

    def reset(self) -> None:
        with self._lock:
            self._scenarios.clear()
            self._history.clear()
            self._payments.clear()

    def record(
        self,
        request: PaymentRequest,
        idempotency_key: str,
    ) -> tuple[ScenarioCreate, int]:
        with self._lock:
            state = self._scenarios.get(request.merchant_order_no)
            if state is None:
                state = ScenarioState(
                    config=ScenarioCreate(merchant_order_no=request.merchant_order_no)
                )
                self._scenarios[request.merchant_order_no] = state
            state.attempts += 1
            recorded = RecordedRequest(
                attempt=state.attempts,
                idempotency_key=idempotency_key,
                request=request,
            )
            self._history.setdefault(request.merchant_order_no, []).append(recorded)
            return state.config, state.attempts

    def get_history(self, merchant_order_no: str) -> list[RecordedRequest]:
        with self._lock:
            return list(self._history.get(merchant_order_no, []))

    def get_payment(self, idempotency_key: str) -> IdempotentPayment | None:
        with self._lock:
            return self._payments.get(idempotency_key)

    def save_payment(
        self,
        idempotency_key: str,
        request: PaymentRequest,
        response: PaymentResponse,
    ) -> None:
        with self._lock:
            self._payments[idempotency_key] = IdempotentPayment(
                request=request,
                response=response,
            )


store = ScenarioStore()
