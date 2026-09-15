"""JSON Schema contract assertion."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from .core import _json_value


def _contract_validation_error(message: str) -> Exception:
    """Import the framework exception only at the point it is needed."""

    from api_testkit.errors import ContractValidationError

    return ContractValidationError(message)


def assert_json_schema(actual_or_response: Any, schema: Mapping[str, Any] | bool | Any) -> None:
    """Validate JSON using the schema's declared draft.

    All validation failures are normalized to ``ContractValidationError`` and
    include both instance and schema paths.  Multiple failures are reported at
    once (capped at ten) to shorten diagnosis cycles.
    """

    instance = _json_value(actual_or_response)
    if not isinstance(schema, (Mapping, bool)):
        raise _contract_validation_error(
            f"JSON Schema must be an object or boolean, got {type(schema).__name__}"
        )

    # Keep the optional-at-import boundary narrow: importing other assertion
    # helpers should not fail merely because a partial development environment
    # has not installed the declared jsonschema dependency yet.
    from jsonschema.exceptions import SchemaError
    from jsonschema.validators import validator_for

    try:
        validator_class = validator_for(schema)
        # jsonschema accepts any Mapping here; its stub narrows to dict, and the
        # isinstance check above has already confirmed Mapping-or-bool.
        validator_class.check_schema(cast("dict[Any, Any]", schema))
        validator = validator_class(schema)
    except (SchemaError, TypeError, ValueError) as exc:
        detail = exc.message if isinstance(exc, SchemaError) else str(exc)
        raise _contract_validation_error(f"invalid JSON Schema: {detail}") from exc

    errors = sorted(
        validator.iter_errors(instance),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if not errors:
        return

    rendered: list[str] = []
    for error in errors[:10]:
        instance_path = "$" + "".join(
            f"[{part}]" if isinstance(part, int) else f".{part}" for part in error.absolute_path
        )
        schema_path = "/".join(str(part) for part in error.absolute_schema_path)
        rendered.append(
            f"instance={instance_path}; schema={schema_path or '<root>'}; error={error.message}"
        )
    if len(errors) > 10:
        rendered.append(f"... and {len(errors) - 10} more violation(s)")
    raise _contract_validation_error("JSON Schema validation failed: " + " | ".join(rendered))


assert_schema = assert_json_schema

__all__ = ["assert_json_schema", "assert_schema"]
