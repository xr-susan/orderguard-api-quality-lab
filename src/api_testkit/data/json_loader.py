"""JSON case loader."""

from __future__ import annotations

import json
from pathlib import Path

from ._common import normalize_document_root, validate_case_sequence
from .models import CaseDataError, CaseSpec


def load_json_cases(path: str | Path) -> list[CaseSpec]:
    """Load and validate cases from a UTF-8 JSON document."""

    source = Path(path)
    try:
        text = source.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise CaseDataError(str(exc), file=str(source)) from exc

    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CaseDataError(
            f"{exc.msg} (column={exc.colno})",
            file=str(source),
            row=exc.lineno,
        ) from exc

    raw_cases = normalize_document_root(raw, path=source)
    return validate_case_sequence(raw_cases, path=source)


load_cases = load_json_cases
