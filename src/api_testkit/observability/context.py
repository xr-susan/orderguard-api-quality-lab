"""Request correlation state based on context-local variables."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any

run_id_var: ContextVar[str | None] = ContextVar("api_testkit_run_id", default=None)
case_id_var: ContextVar[str | None] = ContextVar("api_testkit_case_id", default=None)
request_id_var: ContextVar[str | None] = ContextVar("api_testkit_request_id", default=None)
retry_attempt_var: ContextVar[int | None] = ContextVar("api_testkit_retry_attempt", default=None)


@dataclass(frozen=True, slots=True)
class ExecutionContext:
    run_id: str | None
    case_id: str | None
    request_id: str | None
    retry_attempt: int | None


def get_context() -> ExecutionContext:
    """Return an immutable snapshot of the current execution context."""

    return ExecutionContext(
        run_id=run_id_var.get(),
        case_id=case_id_var.get(),
        request_id=request_id_var.get(),
        retry_attempt=retry_attempt_var.get(),
    )


@contextmanager
def bind_context(
    *,
    run_id: str | None = None,
    case_id: str | None = None,
    request_id: str | None = None,
    retry_attempt: int | None = None,
) -> Iterator[ExecutionContext]:
    """Temporarily bind supplied values and restore prior context afterwards."""

    values: list[tuple[ContextVar[Any], Any]] = []
    if run_id is not None:
        values.append((run_id_var, run_id))
    if case_id is not None:
        values.append((case_id_var, case_id))
    if request_id is not None:
        values.append((request_id_var, request_id))
    if retry_attempt is not None:
        values.append((retry_attempt_var, retry_attempt))
    tokens: list[tuple[ContextVar[Any], Token[Any]]] = []
    try:
        for variable, value in values:
            tokens.append((variable, variable.set(value)))
        yield get_context()
    finally:
        for variable, token in reversed(tokens):
            variable.reset(token)


__all__ = [
    "ExecutionContext",
    "bind_context",
    "case_id_var",
    "get_context",
    "request_id_var",
    "retry_attempt_var",
    "run_id_var",
]
