"""Internal helpers used by the document loaders."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .models import CaseDataError, CaseSource, CaseSpec


def normalize_document_root(raw: Any, *, path: Path) -> list[Any]:
    """Accept either a top-level list or ``{"cases": [...]}``."""

    if raw is None:
        return []
    cases: Any
    if isinstance(raw, Mapping):
        if "cases" not in raw:
            raise CaseDataError(
                "root object must contain a 'cases' list",
                file=str(path),
            )
        cases = raw["cases"]
    else:
        cases = raw

    if not isinstance(cases, list):
        raise CaseDataError(
            "document root must be a list or an object containing a 'cases' list",
            file=str(path),
        )
    return cases


def case_id_from(raw: Any) -> str | None:
    if not isinstance(raw, Mapping):
        return None
    value = raw.get("id", raw.get("case_id"))
    if value is None:
        return None
    rendered = str(value).strip()
    return rendered or None


def validate_case_mapping(
    raw: Any,
    *,
    path: Path,
    row: int,
    sheet: str | None = None,
) -> CaseSpec:
    case_id = case_id_from(raw)
    if not isinstance(raw, Mapping):
        raise CaseDataError(
            f"case entry must be an object, got {type(raw).__name__}",
            file=str(path),
            sheet=sheet,
            row=row,
            case_id=case_id,
        )

    payload = dict(raw)
    payload.pop("source", None)
    if "case_id" in payload and "id" not in payload:
        payload["id"] = payload.pop("case_id")
    payload["source"] = CaseSource(file=str(path), sheet=sheet, row=row)
    try:
        return CaseSpec.model_validate(payload)
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors(include_url=False)
        )
        raise CaseDataError(
            details,
            file=str(path),
            sheet=sheet,
            row=row,
            case_id=case_id,
        ) from exc


def validate_case_sequence(
    raw_cases: Sequence[Any],
    *,
    path: Path,
    first_row: int = 1,
    sheet: str | None = None,
) -> list[CaseSpec]:
    cases: list[CaseSpec] = []
    seen: dict[str, int] = {}
    for offset, raw in enumerate(raw_cases):
        row = first_row + offset
        case = validate_case_mapping(raw, path=path, row=row, sheet=sheet)
        if case.id in seen:
            raise CaseDataError(
                f"duplicate case id; first declared at row={seen[case.id]}",
                file=str(path),
                sheet=sheet,
                row=row,
                case_id=case.id,
            )
        seen[case.id] = row
        cases.append(case)
    return cases
