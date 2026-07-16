"""Safe YAML case loader."""

from __future__ import annotations

from pathlib import Path

import yaml

from ._common import normalize_document_root, validate_case_sequence
from .models import CaseDataError, CaseSpec


def load_yaml_cases(path: str | Path) -> list[CaseSpec]:
    """Load cases from YAML using PyYAML's non-executable safe loader."""

    source = Path(path)
    try:
        text = source.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise CaseDataError(str(exc), file=str(source)) from exc

    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        row = mark.line + 1 if mark is not None else None
        detail = getattr(exc, "problem", None) or str(exc)
        raise CaseDataError(detail, file=str(source), row=row) from exc

    raw_cases = normalize_document_root(raw, path=source)
    # For structured documents, row identifies the one-based case index. YAML
    # parser syntax errors above use the physical source line instead.
    return validate_case_sequence(raw_cases, path=source)


# Short aliases make loader selection convenient without obscuring the format.
load_cases = load_yaml_cases
