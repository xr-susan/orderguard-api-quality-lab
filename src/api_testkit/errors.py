"""Framework-specific exceptions with concise, actionable messages."""

from __future__ import annotations

from pathlib import Path
from typing import Any


class ApiTestkitError(Exception):
    """Base class for errors raised by :mod:`api_testkit`."""


class ConfigurationError(ApiTestkitError):
    """Configuration could not be loaded or validated."""


class CaseDataError(ApiTestkitError):
    """A data-driven case could not be parsed or validated."""

    def __init__(
        self,
        message: str,
        *,
        file: str | Path | None = None,
        sheet: str | None = None,
        row: int | None = None,
        case_id: str | None = None,
        field: str | None = None,
    ) -> None:
        self.file = Path(file) if file is not None else None
        self.sheet = sheet
        self.row = row
        self.case_id = case_id
        self.field = field
        locations: list[str] = []
        if self.file is not None:
            locations.append(str(self.file))
        if sheet is not None:
            locations.append(f"sheet={sheet}")
        if row is not None:
            locations.append(f"row={row}")
        if case_id is not None:
            locations.append(f"case={case_id}")
        if field is not None:
            locations.append(f"field={field}")
        prefix = " | ".join(locations)
        super().__init__(f"{prefix}: {message}" if prefix else message)


class ApiTransportError(ApiTestkitError):
    """An HTTP request failed before a usable response was received."""

    def __init__(
        self,
        message: str,
        *,
        method: str | None = None,
        url: str | None = None,
        attempts: int | None = None,
    ) -> None:
        self.method = method
        self.url = url
        self.attempts = attempts
        details = [part for part in (method, url) if part]
        if attempts is not None:
            details.append(f"attempts={attempts}")
        suffix = f" ({' '.join(details)})" if details else ""
        super().__init__(f"{message}{suffix}")


class AuthenticationError(ApiTestkitError):
    """An authentication credential could not be obtained or applied."""


class ContractValidationError(ApiTestkitError, AssertionError):
    """A response violated its independently maintained API contract."""

    def __init__(
        self,
        message: str,
        *,
        path: str | None = None,
        schema_path: str | None = None,
        actual: Any = None,
    ) -> None:
        self.path = path
        self.schema_path = schema_path
        self.actual = actual
        details = []
        if path:
            details.append(f"instance={path}")
        if schema_path:
            details.append(f"schema={schema_path}")
        suffix = f" ({', '.join(details)})" if details else ""
        super().__init__(f"{message}{suffix}")


class MockControlError(ApiTestkitError):
    """A mock scenario could not be registered, queried, or cleaned up."""
