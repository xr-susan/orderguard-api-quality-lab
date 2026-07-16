from __future__ import annotations

from pathlib import Path

import pytest

from api_testkit.config import Settings, load_settings
from api_testkit.errors import ConfigurationError


def test_defaults_load_without_configuration_directory(tmp_path: Path) -> None:
    settings = load_settings(tmp_path, environ={})

    assert settings.env == "local"
    assert settings.base_url == "http://127.0.0.1:8000"
    assert settings.timeout.connect == 5.0
    assert settings.retry.retry_status_codes == frozenset({429, 502, 503, 504})


def test_layer_precedence_is_deterministic(tmp_path: Path) -> None:
    (tmp_path / "base.yaml").write_text(
        """
env: local
base_url: http://base.example
timeout:
  read: 11
  connect: 4
retry:
  max_attempts: 2
""",
        encoding="utf-8",
    )
    (tmp_path / "ci.yaml").write_text(
        """
base_url: http://ci.example/
timeout:
  read: 22
retry:
  max_attempts: 4
""",
        encoding="utf-8",
    )

    settings = load_settings(
        tmp_path,
        env="ci",
        environ={
            "ORDERGUARD_BASE_URL": "http://environment.example/",
            "ORDERGUARD_TIMEOUT__READ": "33",
            "ORDERGUARD_RETRY__MAX_ATTEMPTS": "5",
        },
        overrides={"retry": {"max_attempts": 6}},
    )

    assert settings.env == "ci"
    assert settings.base_url == "http://environment.example"
    assert settings.timeout.connect == 4
    assert settings.timeout.read == 33
    assert settings.retry.max_attempts == 6


def test_environment_selects_environment_file(tmp_path: Path) -> None:
    (tmp_path / "base.yaml").write_text("base_url: http://base.example\n", encoding="utf-8")
    (tmp_path / "qa.yaml").write_text("base_url: http://qa.example\n", encoding="utf-8")

    settings = load_settings(tmp_path, environ={"ORDERGUARD_ENV": "qa"})

    assert settings.env == "qa"
    assert settings.base_url == "http://qa.example"


def test_explicit_environment_selector_outranks_environment_variable(
    tmp_path: Path,
) -> None:
    (tmp_path / "ci.yaml").write_text("base_url: http://ci.example\n", encoding="utf-8")
    (tmp_path / "qa.yaml").write_text("base_url: http://qa.example\n", encoding="utf-8")

    settings = load_settings(tmp_path, env="ci", environ={"ORDERGUARD_ENV": "qa"})

    assert settings.env == "ci"
    assert settings.base_url == "http://ci.example"


def test_secret_in_yaml_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "base.yaml").write_text("auth_token: should-not-be-committed\n", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="must come from an environment"):
        load_settings(tmp_path, environ={})


def test_secret_from_environment_is_supported(tmp_path: Path) -> None:
    settings = load_settings(tmp_path, environ={"ORDERGUARD_AUTH_TOKEN": "runtime-secret"})

    assert settings.auth_token is not None
    assert settings.auth_token.get_secret_value() == "runtime-secret"
    assert "runtime-secret" not in repr(settings)


def test_yaml_uses_safe_loader(tmp_path: Path) -> None:
    (tmp_path / "base.yaml").write_text(
        "value: !!python/object/apply:os.system ['echo unsafe']\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match="cannot read configuration"):
        load_settings(tmp_path, environ={})


def test_invalid_root_and_validation_error_are_actionable(tmp_path: Path) -> None:
    (tmp_path / "base.yaml").write_text("- not\n- a mapping\n", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="root must be a mapping"):
        load_settings(tmp_path, environ={})

    (tmp_path / "base.yaml").write_text("timeout:\n  read: never\n", encoding="utf-8")
    with pytest.raises(ConfigurationError, match=r"timeout\.read"):
        load_settings(tmp_path, environ={})


def test_missing_required_base_file_is_actionable(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match=r"base\.yaml"):
        load_settings(tmp_path, environ={}, require_base=True)


@pytest.mark.parametrize("url", ["localhost:8000", "ftp://example.test"])
def test_settings_reject_non_http_base_url(url: str) -> None:
    with pytest.raises(ValueError, match="base_url"):
        Settings(base_url=url)


def test_retry_status_codes_accept_comma_separated_environment_value(
    tmp_path: Path,
) -> None:
    settings = load_settings(
        tmp_path,
        environ={"ORDERGUARD_RETRY__RETRY_STATUS_CODES": "429, 503"},
    )

    assert settings.retry.retry_status_codes == frozenset({429, 503})
