"""Minimal authentication provider abstractions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from api_testkit.errors import AuthenticationError


@runtime_checkable
class AuthProvider(Protocol):
    """Supplies the current bearer token for a logical request."""

    def get_token(self) -> str | None:
        """Return a token, or ``None`` for an unauthenticated request."""


@dataclass(frozen=True, slots=True)
class StaticTokenProvider:
    token: str

    def get_token(self) -> str:
        if not self.token.strip():
            raise AuthenticationError("authentication token is empty")
        return self.token


@dataclass(frozen=True, slots=True)
class CallableTokenProvider:
    provider: Callable[[], str | None]

    def get_token(self) -> str | None:
        try:
            return self.provider()
        except AuthenticationError:
            raise
        except Exception as exc:
            raise AuthenticationError("authentication provider failed") from exc


def coerce_auth_provider(
    auth: str | AuthProvider | Callable[[], str | None] | None,
) -> AuthProvider | None:
    if auth is None:
        return None
    if isinstance(auth, str):
        return StaticTokenProvider(auth)
    if isinstance(auth, AuthProvider):
        return auth
    if callable(auth):
        return CallableTokenProvider(auth)
    raise TypeError("auth must be a token, AuthProvider, callable, or None")


__all__ = [
    "AuthProvider",
    "CallableTokenProvider",
    "StaticTokenProvider",
    "coerce_auth_provider",
]
