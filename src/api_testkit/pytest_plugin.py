"""Optional pytest integration for settings, context, and data-driven cases."""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from api_testkit.config import Settings, load_settings
from api_testkit.http import ApiClient
from api_testkit.observability.context import bind_context

if TYPE_CHECKING:
    from api_testkit.data.models import CaseSpec


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("api-testkit")
    group.addoption(
        "--api-env",
        action="store",
        default=None,
        help="configuration environment (loads config/<env>.yaml)",
    )
    group.addoption(
        "--api-config-dir",
        action="store",
        default="config",
        help="directory containing base.yaml and environment YAML",
    )
    group.addoption(
        "--api-base-url",
        action="store",
        default=None,
        help="override the configured target base URL",
    )
    group.addoption(
        "--case-data",
        action="store",
        default=None,
        help="default YAML, JSON, or Excel source for case_spec parametrization",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "case_data(path): load validated CaseSpec values from YAML, JSON, or Excel",
    )
    config.addinivalue_line("markers", "external: calls a non-local public API")
    config.addinivalue_line("markers", "resilience: dependency failure and retry scenarios")


def _load_case_source(path: str | Path) -> list[CaseSpec]:
    # Import lazily: projects not using data files need not import Excel support.
    from api_testkit.data import load_cases

    return load_cases(path)


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if "case_spec" not in metafunc.fixturenames:
        return
    marker = metafunc.definition.get_closest_marker("case_data")
    marker_path = marker.args[0] if marker and marker.args else None
    option_path = metafunc.config.getoption("case_data")
    path = marker_path or option_path
    if path is None:
        raise pytest.UsageError(
            f"{metafunc.definition.nodeid} requests case_spec but has no "
            "@pytest.mark.case_data(path) or --case-data option"
        )
    cases = _load_case_source(path)
    metafunc.parametrize("case_spec", cases, ids=[case.id for case in cases])


@pytest.fixture(scope="session")
def api_settings(pytestconfig: pytest.Config) -> Settings:
    base_url = pytestconfig.getoption("api_base_url")
    overrides = {"base_url": base_url} if base_url else None
    return load_settings(
        pytestconfig.getoption("api_config_dir"),
        env=pytestconfig.getoption("api_env"),
        overrides=overrides,
    )


@pytest.fixture(scope="session")
def api_run_id() -> str:
    return os.getenv("ORDERGUARD_RUN_ID", str(uuid.uuid4()))


@pytest.fixture
def api_client(api_settings: Settings) -> Any:
    token = (
        api_settings.auth_token.get_secret_value() if api_settings.auth_token is not None else None
    )
    with ApiClient(
        api_settings.base_url,
        auth=token,
        timeout=api_settings.timeout,
        retry=api_settings.retry,
    ) as client:
        yield client


@pytest.fixture(autouse=True)
def _api_test_context(request: pytest.FixtureRequest, api_run_id: str) -> Any:
    case_id = request.node.name
    callspec = getattr(request.node, "callspec", None)
    if callspec is not None and "case_spec" in callspec.params:
        case_id = callspec.params["case_spec"].id
    with bind_context(run_id=api_run_id, case_id=case_id):
        yield


__all__ = [
    "pytest_addoption",
    "pytest_configure",
    "pytest_generate_tests",
]
