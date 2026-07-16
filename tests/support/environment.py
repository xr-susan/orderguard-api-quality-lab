from __future__ import annotations

import os
from dataclasses import dataclass

from api_testkit.config import Settings


@dataclass(frozen=True)
class TestEnvironment:
    base_url: str
    payment_mock_admin_url: str
    username: str
    password: str

    @classmethod
    def from_settings(cls, settings: Settings) -> TestEnvironment:
        return cls(
            base_url=settings.base_url,
            payment_mock_admin_url=os.getenv(
                "PAYMENT_MOCK_ADMIN_URL", "http://127.0.0.1:8001"
            ).rstrip("/"),
            username=os.getenv("TEST_USERNAME", "demo"),
            password=os.getenv("TEST_PASSWORD", "demo123"),
        )
