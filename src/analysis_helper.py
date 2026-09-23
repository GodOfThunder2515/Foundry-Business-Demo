"""Small, generic guardrails for Code Interpreter analysis outputs."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any


GROUP_LIMIT = 15
DETAIL_LIMIT = 10
COLUMN_LIMIT = 12


def find_uploaded_file(logical_name: str, search_root: Path) -> Path:
    """Resolve an uploaded file whose mounted name may start with a file ID."""
    exact = search_root / logical_name
    if exact.is_file():
        return exact

    matches = sorted(path for path in search_root.glob(f"*-{logical_name}") if path.is_file())
    if not matches:
        raise FileNotFoundError(f"Uploaded file not found: {logical_name}")
    if len(matches) > 1:
        raise ValueError(f"Multiple uploaded files match {logical_name}: {matches}")
    return matches[0]


def parse_yyyymmdd(value: object) -> date | None:
    """Parse integer-like Gold date keys without depending on dim_date coverage."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError(f"Expected yyyyMMdd date key, got {value!r}")
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    text = str(value)
    try:
        return datetime.strptime(text, "%Y%m%d").date()
    except ValueError as error:
        raise ValueError(f"Expected yyyyMMdd date key, got {value!r}") from error


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _sorted_records(
    records: list[dict[str, object]], sort_spec: list[tuple[str, str]]
) -> list[dict[str, object]]:
    result = list(records)
    for column, direction in sort_spec:
        if direction not in {"asc", "desc"}:
            raise ValueError(f"Invalid sort direction for {column}: {direction}")
        missing = [index for index, row in enumerate(result) if column not in row]
        if missing:
            raise KeyError(f"Sort column {column!r} missing from record {missing[0]}")

    # Stable sorts in reverse priority order support mixed directions.
    for column, direction in reversed(sort_spec):
        populated = [row for row in result if row[column] is not None]
        empty = [row for row in result if row[column] is None]
        populated.sort(key=lambda row: row[column], reverse=direction == "desc")
        result = populated + empty
    return result


def build_analysis_result(
    *,
    matched_rows: int,
    filters: list[str],
    data_as_of: str,
    summary_metrics: dict[str, object],
    records: list[dict[str, object]],
    sort_spec: list[tuple[str, str]],
    detail: bool = False,
    offset: int = 0,
    columns: list[str] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, object]:
    """Sort, page, cap, and normalize the only result returned to the model."""
    if matched_rows < 0:
        raise ValueError("matched_rows cannot be negative")
    if offset < 0:
        raise ValueError("offset cannot be negative")

    ordered = _sorted_records(records, sort_spec)
    selected_columns = list(columns) if columns is not None else (
        list(ordered[0])[:COLUMN_LIMIT] if ordered else []
    )
    if len(selected_columns) > COLUMN_LIMIT:
        selected_columns = selected_columns[:COLUMN_LIMIT]
    for column in selected_columns:
        missing = [index for index, row in enumerate(ordered) if column not in row]
        if missing:
            raise KeyError(f"Output column {column!r} missing from record {missing[0]}")

    limit = DETAIL_LIMIT if detail else GROUP_LIMIT
    page = ordered[offset : offset + limit]
    projected = [{column: row[column] for column in selected_columns} for row in page]

    return {
        "population": {
            "matched_rows": matched_rows,
            "filters": list(filters),
            "data_as_of": data_as_of,
        },
        "summary_metrics": _json_safe(summary_metrics),
        "top_results": _json_safe(projected),
        "warnings": list(warnings or []),
        "truncated": offset + len(page) < len(ordered),
    }
