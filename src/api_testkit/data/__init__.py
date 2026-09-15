"""Public data-driven testing API."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from api_testkit.errors import CaseDataError

from .excel_loader import load_excel_cases
from .json_loader import load_json_cases
from .models import (
    CaseSource,
    CaseSpec,
    DataLoadError,
    ExpectedSpec,
    RequestSpec,
)
from .yaml_loader import load_yaml_cases

# Extension -> loader. Excel has two common extensions; YAML has two spellings.
_SUFFIX_LOADERS: dict[str, Callable[[str | Path], list[CaseSpec]]] = {
    ".yaml": load_yaml_cases,
    ".yml": load_yaml_cases,
    ".json": load_json_cases,
    ".xlsx": load_excel_cases,
    ".xlsm": load_excel_cases,
}


def load_cases(path: str | Path) -> list[CaseSpec]:
    """Load cases from any supported source, choosing the loader by file suffix.

    This is the entry point used by the ``case_data`` marker and the
    ``--case-data`` option, both of which accept YAML, JSON, or Excel.
    """

    source = Path(path)
    loader = _SUFFIX_LOADERS.get(source.suffix.lower())
    if loader is None:
        supported = ", ".join(sorted(_SUFFIX_LOADERS))
        found = source.suffix or "no extension"
        raise CaseDataError(
            f"unsupported case source ({found}); expected one of {supported}",
            file=str(source),
        )
    return loader(source)


__all__ = [
    "CaseDataError",
    "CaseSource",
    "CaseSpec",
    "DataLoadError",
    "ExpectedSpec",
    "RequestSpec",
    "load_cases",
    "load_excel_cases",
    "load_json_cases",
    "load_yaml_cases",
]
