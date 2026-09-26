"""Small, generic guardrails for Code Interpreter analysis outputs."""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any


GROUP_LIMIT = 15
DETAIL_LIMIT = 10
COLUMN_LIMIT = 12


DISPLAY_COLUMN_LIMIT = 8

MOUNT_ROOT = Path("/mnt/data")
FORMATS = {"inr", "pct", "pct100", "int", "num", "date"}
# Snake-case codes (credit_limit, QUALITY_HELD_STOCK) that table cells show as words.
CODE_VALUE = re.compile(r"[a-z]+(?:_[a-z0-9]+)+|[A-Z]+(?:_[A-Z0-9]+)+")
SITE_NAMES = {
    "S001": "Pune",
    "S002": "Nashik",
    "S003": "Ahmedabad",
    "S004": "Bengaluru",
    "S005": "Hyderabad",
    "S006": "Delhi",
    "S007": "Kolkata",
    "S008": "Indore",
}
SIGNAL_LABELS = {
    "LOGISTICS_EXCEPTION": "Logistics exception",
    "QUALITY_HELD_STOCK": "Quality-held stock",
    "PRODUCT_SITE_CAPACITY_PRESSURE": "Site capacity pressure",
    "LOW_ALLOCATION_RATIO": "Low stock allocation",
    "COMMERCIAL_HOLD": "Commercial hold",
    "POSSIBLE_INVENTORY_SHORTAGE": "Possible stock shortage",
}
_RANK = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}


# Gold tables documented in the catalog but not uploaded, to stay within Code
# Interpreter's 20-file limit: unused (region), superseded (date) or rarely needed.
NOT_UPLOADED = frozenset({"dim_date", "dim_region", "fact_inventory_transactions"})


def catalog_tables(catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Flatten dataset_catalog.json into the 17 loaded tables: Gold under "tables", risk under "risk_tables"."""
    merged: dict[str, dict[str, Any]] = {}
    for group, key in (("gold", "tables"), ("risk", "risk_tables")):
        for name, entry in catalog.get(key, {}).items():
            if name not in NOT_UPLOADED:
                merged[name] = {**entry, "group": group}
    return merged


SEGMENT_PREFIXES = {
    "product_family": "Family",
    "order_priority": "Priority",
    "service_level": "Service level",
}


def segment_label(segment_type: str, segment_value: str) -> str:
    """Business label for a model-metrics segment, e.g. ("site_id", "S005") -> "Plant: Hyderabad"."""
    if segment_type == "overall":
        return "All scored lines"
    if segment_type == "site_id":
        return f"Plant: {SITE_NAMES.get(segment_value, segment_value)}"
    if segment_type == "warehouse_id":
        # Two warehouses per plant: odd numbers hold raw material, even numbers finished goods.
        number = int(segment_value.removeprefix("WH"))
        site = SITE_NAMES.get(f"S{(number + 1) // 2:03d}", segment_value)
        kind = "finished goods" if number % 2 == 0 else "raw material"
        return f"Warehouse: {site} {kind}"
    prefix = SEGMENT_PREFIXES.get(segment_type, segment_type.replace("_", " ").capitalize())
    return f"{prefix}: {segment_value.replace('_', ' ').capitalize()}"


def main_signal_by_line(evidence: Any) -> dict[str, str]:
    """Pick each line's strongest operational signal (severity, then confidence) as a business label."""
    records = evidence.to_dict(orient="records") if hasattr(evidence, "to_dict") else list(evidence)
    best: dict[str, tuple[int, int, str]] = {}
    for row in records:
        key = (_RANK.get(row["severity"], 3), _RANK.get(row["confidence"], 3), row["evidence_code"])
        line = row["sales_order_line_id"]
        if line not in best or key < best[line]:
            best[line] = key
    return {line: SIGNAL_LABELS.get(key[2], key[2]) for line, key in best.items()}


def find_uploaded_file(logical_name: str, search_root: Path = MOUNT_ROOT) -> Path:
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


def _is_missing(value: object) -> bool:
    # NaN is the only value that is not equal to itself.
    return value is None or value == "" or value != value


def _as_date(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if hasattr(value, "to_pydatetime"):
        return value.to_pydatetime().date()
    text = str(value).strip()
    if text.replace(".0", "").isdigit() and len(text.replace(".0", "")) == 8:
        return parse_yyyymmdd(text.replace(".0", ""))
    return datetime.fromisoformat(text[:10]).date()


def _format_value(value: object, style: str | None) -> str:
    if _is_missing(value):
        return "—"
    if hasattr(value, "item") and not isinstance(value, (str, date)):
        value = value.item()  # numpy scalar -> Python scalar
    if isinstance(value, Decimal):
        value = float(value)
    if style == "date":
        day = _as_date(value)
        suffix = "" if day.year == 2026 else f" {day.year}"
        return f"{day.day} {day:%b}{suffix}"
    if style == "inr":
        amount = float(value)
        sign = "-" if amount < 0 else ""
        amount = abs(amount)
        if amount >= 1_000_000:
            return f"{sign}₹{amount / 1_000_000:.2f}M"
        if amount >= 1_000:
            return f"{sign}₹{amount / 1_000:.1f}K"
        return f"{sign}₹{amount:,.0f}"
    if style == "pct":
        return f"{float(value) * 100:.1f}%"
    if style == "pct100":
        return f"{float(value):.1f}%"
    if style == "int":
        return f"{int(round(float(value))):,}"
    if style == "num" or isinstance(value, float):
        return f"{float(value):,.2f}"
    if isinstance(value, int) and not isinstance(value, bool):
        return f"{value:,}"
    text = str(value)
    if CODE_VALUE.fullmatch(text):
        # A status, hold or evidence code such as credit_limit: show it as words.
        return text.replace("_", " ").capitalize()
    text = CODE_VALUE.sub(lambda match: match.group().replace("_", " "), text)
    return text.replace("|", "/").replace("\n", " ")


def format_table(
    rows: Any,
    columns: list[str],
    *,
    labels: dict[str, str] | None = None,
    formats: dict[str, str] | None = None,
    limit: int = DETAIL_LIMIT,
    offset: int = 0,
    total: int | None = None,
) -> str:
    """Render already-sorted rows as a capped Markdown table for the final answer."""
    records = rows.to_dict(orient="records") if hasattr(rows, "to_dict") else list(rows)
    if len(columns) > DISPLAY_COLUMN_LIMIT:
        raise ValueError(
            f"At most {DISPLAY_COLUMN_LIMIT} columns may be displayed, got {len(columns)}; "
            "keep the columns a manager needs"
        )
    formats = formats or {}
    unknown = {style for style in formats.values() if style not in FORMATS}
    if unknown:
        raise ValueError(f"Unknown format {sorted(unknown)}; use one of {sorted(FORMATS)}")
    if offset < 0:
        raise ValueError("offset cannot be negative")
    for column in columns:
        if records and column not in records[0]:
            raise KeyError(f"Column {column!r} is not in the rows")

    labels = labels or {}
    page = records[offset : offset + min(limit, GROUP_LIMIT)]
    lines = [
        "| " + " | ".join(labels.get(column, column) for column in columns) + " |",
        "|" + "---|" * len(columns),
    ]
    for row in page:
        cells = (_format_value(row[column], formats.get(column)) for column in columns)
        lines.append("| " + " | ".join(cells) + " |")
    population = len(records) if total is None else total
    first = offset + 1 if page else 0
    lines.append("")
    lines.append(f"Rows {first}–{offset + len(page)} of {population:,}")
    return "\n".join(lines)


def show_table(rows: Any, columns: list[str], **options: Any) -> None:
    """Print the Markdown table; copy it into the answer exactly as printed."""
    print(format_table(rows, columns, **options))


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
