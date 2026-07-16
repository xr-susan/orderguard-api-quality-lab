from pathlib import Path
from typing import Any

import pytest

from api_testkit.assertions import assert_response
from api_testkit.data import (
    CaseSpec,
    load_excel_cases,
    load_json_cases,
    load_yaml_cases,
)

DATA_ROOT = Path(__file__).parents[2] / "data"


def _load_cases() -> list[CaseSpec]:
    return [
        *load_yaml_cases(DATA_ROOT / "yaml" / "public_cases.yaml"),
        *load_json_cases(DATA_ROOT / "json" / "public_cases.json"),
        *load_excel_cases(DATA_ROOT / "excel" / "public_cases.xlsx", sheet_name="cases"),
    ]


def _parameter(case: CaseSpec) -> Any:
    marks = [getattr(pytest.mark, marker) for marker in case.markers]
    return pytest.param(case, id=case.id, marks=marks)


@pytest.mark.functional
@pytest.mark.parametrize("case", [_parameter(case) for case in _load_cases()])
def test_data_driven_case(api_client, case: CaseSpec) -> None:
    response = api_client.request(
        case.request.method,
        case.request.path,
        headers=case.request.headers,
        params=case.request.query,
        json=case.request.json_body,
        timeout=case.request.timeout_seconds,
    )

    assert_response(response, case.expected)
