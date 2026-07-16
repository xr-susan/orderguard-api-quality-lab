"""Load settings from defaults, layered YAML, environment, and overrides."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from api_testkit.config.models import Settings
from api_testkit.errors import ConfigurationError

ENV_PREFIX = "ORDERGUARD_"
_YAML_SECRET_KEYS = {
    "auth_token",
    "password",
    "secret",
    "signing_secret",
    "api_key",
    "access_token",
}


def _deep_merge(base: Mapping[str, Any], overlay: Mapping[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overlay.items():
        current = merged.get(key)
        if isinstance(current, Mapping) and isinstance(value, Mapping):
            merged[key] = _deep_merge(current, value)
        else:
            merged[key] = value
    return merged


def _load_yaml(path: Path, *, required: bool) -> dict[str, Any]:
    if not path.exists():
        if required:
            raise ConfigurationError(f"configuration file not found: {path}")
        return {}
    try:
        with path.open("r", encoding="utf-8") as stream:
            raw = yaml.safe_load(stream)
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigurationError(f"cannot read configuration file {path}: {exc}") from exc
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise ConfigurationError(f"configuration root must be a mapping: {path}")
    result = {str(key): value for key, value in raw.items()}
    secret_path = _find_secret(result)
    if secret_path:
        raise ConfigurationError(
            f"secret setting '{secret_path}' must come from an environment variable, not {path}"
        )
    return result


def _find_secret(value: object, prefix: str = "") -> str | None:
    if not isinstance(value, Mapping):
        return None
    for raw_key, nested in value.items():
        key = str(raw_key)
        path = f"{prefix}.{key}" if prefix else key
        if key.lower() in _YAML_SECRET_KEYS:
            return path
        found = _find_secret(nested, path)
        if found:
            return found
    return None


def _parse_environment_value(value: str) -> Any:
    stripped = value.strip()
    if not stripped:
        return value
    if stripped[0] in '[{"' or stripped.lower() in {"true", "false", "null"}:
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            return value
    return value


def _environment_overlay(environ: Mapping[str, str]) -> dict[str, Any]:
    overlay: dict[str, Any] = {}
    prefix_length = len(ENV_PREFIX)
    for name, raw_value in environ.items():
        if not name.upper().startswith(ENV_PREFIX):
            continue
        path = [part.lower() for part in name[prefix_length:].split("__") if part]
        if not path:
            continue
        cursor = overlay
        for part in path[:-1]:
            child = cursor.get(part)
            if not isinstance(child, dict):
                child = {}
                cursor[part] = child
            cursor = child
        cursor[path[-1]] = _parse_environment_value(raw_value)
    return overlay


def _validation_message(exc: ValidationError) -> str:
    errors: list[str] = []
    for item in exc.errors(include_url=False):
        location = ".".join(str(part) for part in item["loc"])
        errors.append(f"{location}: {item['msg']}")
    return "; ".join(errors)


def load_settings(
    config_dir: str | Path = "config",
    *,
    env: str | None = None,
    environ: Mapping[str, str] | None = None,
    overrides: Mapping[str, Any] | None = None,
    require_base: bool = False,
) -> Settings:
    """Load and validate settings using deterministic precedence.

    Precedence, lowest to highest, is model defaults, ``base.yaml``, the
    selected ``{env}.yaml``, ``ORDERGUARD_*`` variables, and explicit
    ``overrides`` (used by pytest command-line options).
    """

    directory = Path(config_dir)
    environment = os.environ if environ is None else environ
    base = _load_yaml(directory / "base.yaml", required=require_base)
    selected_env = env or environment.get(f"{ENV_PREFIX}ENV") or str(base.get("env", "local"))
    env_values = _load_yaml(directory / f"{selected_env}.yaml", required=False)
    values = _deep_merge(base, env_values)
    values = _deep_merge(values, _environment_overlay(environment))
    # The selector identifies both the file and the resulting runtime environment.
    # An explicit selector (pytest CLI) outranks ORDERGUARD_ENV.
    values["env"] = selected_env
    if overrides:
        values = _deep_merge(values, overrides)
    try:
        # Environment values were merged explicitly so YAML never outranks them.
        return Settings.model_validate(values)
    except ValidationError as exc:
        raise ConfigurationError(
            f"invalid configuration for environment '{selected_env}': {_validation_message(exc)}"
        ) from exc


__all__ = ["ENV_PREFIX", "load_settings"]
