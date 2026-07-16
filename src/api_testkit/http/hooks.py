"""Typed diagnostics passed to optional request lifecycle hooks."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import httpx


@dataclass(frozen=True, slots=True)
class RequestObservation:
    request: httpx.Request
    attempt: int


@dataclass(frozen=True, slots=True)
class ResponseObservation:
    response: httpx.Response
    attempt: int
    elapsed_seconds: float


RequestHook = Callable[[RequestObservation], None]
ResponseHook = Callable[[ResponseObservation], None]


__all__ = [
    "RequestHook",
    "RequestObservation",
    "ResponseHook",
    "ResponseObservation",
]
