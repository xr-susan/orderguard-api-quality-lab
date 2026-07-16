"""Small HMAC-signed bearer token implementation for the demo service."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

DEMO_USERS = {
    "demo": "demo123",
    "test": "test123",
}

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class CurrentUser:
    username: str


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def issue_token(username: str, secret: str, ttl_seconds: int) -> str:
    payload = json.dumps(
        {"sub": username, "exp": int(time.time()) + ttl_seconds},
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    encoded_payload = _b64encode(payload)
    signature = hmac.new(secret.encode(), encoded_payload.encode(), hashlib.sha256).digest()
    return f"{encoded_payload}.{_b64encode(signature)}"


def verify_token(token: str, secret: str) -> CurrentUser:
    try:
        encoded_payload, encoded_signature = token.split(".", maxsplit=1)
        expected = hmac.new(secret.encode(), encoded_payload.encode(), hashlib.sha256).digest()
        supplied = _b64decode(encoded_signature)
        if not hmac.compare_digest(expected, supplied):
            raise ValueError("signature mismatch")
        payload = json.loads(_b64decode(encoded_payload))
        username = payload["sub"]
        expires_at = int(payload["exp"])
        if expires_at <= int(time.time()) or username not in DEMO_USERS:
            raise ValueError("expired or unknown subject")
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_TOKEN", "message": "Bearer token is invalid or expired"},
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    return CurrentUser(username=username)


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> CurrentUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_REQUIRED", "message": "Bearer token is required"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    return verify_token(credentials.credentials, request.app.state.settings.auth_secret)
