"""Regenerate the committed Excel adapter examples deterministically."""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font

OUTPUT = Path(__file__).parents[1] / "tests" / "data" / "excel" / "public_cases.xlsx"


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "cases"
    headers = [
        "id",
        "name",
        "markers",
        "method",
        "path",
        "headers",
        "body",
        "status",
        "json_paths",
    ]
    sheet.append(headers)
    sheet.append(
        [
            "DD-XLSX-PRODUCT-001",
            "product response has a positive stock value source",
            "functional",
            "GET",
            "/products",
            "{}",
            None,
            200,
            '{"$[0].name":"Mechanical Keyboard"}',
        ]
    )
    sheet.append(
        [
            "DD-XLSX-AUTH-001",
            "wrong password is rejected",
            "functional,security",
            "POST",
            "/auth/token",
            "{}",
            '{"username":"demo","password":"wrong-from-excel"}',
            401,
            '{"$.detail.code":"INVALID_CREDENTIALS"}',
        ]
    )
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for column in sheet.columns:
        width = min(max(len(str(cell.value or "")) for cell in column) + 2, 60)
        sheet.column_dimensions[column[0].column_letter].width = width
    workbook.save(OUTPUT)


if __name__ == "__main__":
    main()
