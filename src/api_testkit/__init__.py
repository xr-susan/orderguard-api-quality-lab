"""Reusable building blocks for black-box API tests.

The package deliberately contains no domain-specific clients.  Projects use the
small primitives exported here to build their own business-facing test layer.
"""

from api_testkit.config import Settings, load_settings
from api_testkit.errors import (
    ApiTestkitError,
    ApiTransportError,
    AuthenticationError,
    CaseDataError,
    ConfigurationError,
    ContractValidationError,
    MockControlError,
)

__all__ = [
    "ApiTestkitError",
    "ApiTransportError",
    "AuthenticationError",
    "CaseDataError",
    "ConfigurationError",
    "ContractValidationError",
    "MockControlError",
    "Settings",
    "load_settings",
]
