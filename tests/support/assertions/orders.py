from __future__ import annotations

from typing import Any


def assert_order_state(
    payload: dict[str, Any],
    expected_status: str,
    *,
    reservation_released: bool | None = None,
) -> None:
    assert payload["status"] == expected_status
    if reservation_released is not None:
        assert payload["reservation_released"] is reservation_released
