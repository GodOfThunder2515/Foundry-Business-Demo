"""Small deterministic checks for the manufacturing golden questions."""

from __future__ import annotations

import csv
import json
import re
import time
from collections.abc import Callable
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


EVALUATION_BLOCK = re.compile(
    r"```evaluation_json\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE
)
RECORD_ID = re.compile(r"\bSOL?\d{9}\b")
WORD = re.compile(r"\w+")
# Any snake_case column, status or evidence code; the model's own name is allowed.
CODE_TOKEN = re.compile(r"\b[A-Za-z]+(?:_[A-Za-z0-9]+)+\b")
ALLOWED_CODES = frozenset({"logistic_regression"})
NEGATIONS = ("not ", "no ", "never ", "n't ", "rather than ")


def _claim_asserted(lowered: str, claim: str) -> bool:
    """True if the claim appears without a negation just before it ("not live predictions")."""
    needle = claim.casefold()
    start = lowered.find(needle)
    while start != -1:
        if not any(negation in lowered[max(0, start - 15):start] for negation in NEGATIONS):
            return True
        start = lowered.find(needle, start + 1)
    return False


# Method narration and raw column names that the answer style forbids.
STYLE_PHRASES = (
    "what i did",
    "what i computed",
    "analysis steps",
    "i will now",
    "next i will",
    "operational_queue_status",
    "within_14_day_window",
    "intervention_priority_score",
    "late_probability",
    "predicted_late_flag",
    "open_not_yet_due",
    "logistics_exception",
    "quality_held_stock",
    "product_site_capacity_pressure",
    "low_allocation_ratio",
    "commercial_hold",
    "if you want",
    "(recorded.)",
    "(printed",
    "/mnt/data",
    "assistant-",
    "footnote:",
)


def load_known_ids(sales_csv: Path) -> set[str]:
    """Collect every real sales-order and line ID so fabricated IDs can be detected."""
    known: set[str] = set()
    with sales_csv.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            known.add(row["sales_order_line_id"])
            known.add(row["sales_order_id"])
    return known


def _prose_word_count(text: str) -> int:
    prose = [line for line in text.splitlines() if not line.lstrip().startswith("|")]
    return len(WORD.findall("\n".join(prose)))


def group_demo_cases(cases: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for case in cases:
        name = case.get("conversation_group")
        if not isinstance(name, str) or not name:
            raise ValueError(f"Demo case {case.get('id', '<unknown>')} has no conversation_group")
        groups.setdefault(name, []).append(case)
    return list(groups.items())


def _markdown_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def extract_markdown_tables(text: str) -> list[dict[str, Any]]:
    lines = text.splitlines()
    tables: list[dict[str, Any]] = []
    index = 0
    while index + 1 < len(lines):
        headers = _markdown_cells(lines[index]) if "|" in lines[index] else []
        separators = _markdown_cells(lines[index + 1]) if "|" in lines[index + 1] else []
        is_separator = bool(headers) and len(headers) == len(separators) and all(
            re.fullmatch(r":?-{3,}:?", cell.replace(" ", ""))
            for cell in separators
        )
        if not is_separator:
            index += 1
            continue
        rows: list[dict[str, str]] = []
        index += 2
        while index < len(lines) and "|" in lines[index]:
            cells = _markdown_cells(lines[index])
            if len(cells) != len(headers):
                break
            rows.append(dict(zip(headers, cells)))
            index += 1
        tables.append({"columns": headers, "rows": rows})
    return tables


def _normalized_fragment(value: object) -> str:
    return re.sub(r"[^a-z0-9.\-]", "", str(value).casefold())


def evaluate_demo_response(
    case: dict[str, Any],
    text: str,
    code_interpreter_called: bool,
    *,
    prior_record_ids: set[str] | None = None,
    known_ids: set[str] | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    if case.get("requires_code_interpreter") and not code_interpreter_called:
        errors.append("Code Interpreter was not invoked")

    if known_ids is not None:
        unknown = sorted(set(RECORD_ID.findall(text)) - known_ids)
        if unknown:
            errors.append(f"Unknown record IDs (possible fabrication): {', '.join(unknown)}")
    words = _prose_word_count(text)
    if case.get("max_words") and words > case["max_words"]:
        errors.append(f"Answer too long: {words} words > {case['max_words']}")

    lowered = text.casefold()
    if case.get("style_checks", True):
        for phrase in STYLE_PHRASES:
            if phrase in lowered:
                errors.append(f"Style: method narration or raw column name present: {phrase}")
        codes = {match.casefold() for match in CODE_TOKEN.findall(text)}
        for code in sorted(codes - set(STYLE_PHRASES) - ALLOWED_CODES):
            errors.append(f"Style: raw code present: {code}")
    for qualifier in case.get("required_qualifiers", []):
        alternatives = qualifier if isinstance(qualifier, list) else [qualifier]
        if not any(str(value).casefold() in lowered for value in alternatives):
            errors.append(f"Required qualifier missing: {qualifier}")
    for claim in case.get("forbidden_claims", []):
        if _claim_asserted(lowered, claim):
            errors.append(f"Forbidden claim present: {claim}")

    normalized_text = _normalized_fragment(text)
    for expected in case.get("required_values", []):
        alternatives = expected if isinstance(expected, list) else [expected]
        if not any(_normalized_fragment(value) in normalized_text for value in alternatives):
            errors.append(f"Required value missing: {expected}")

    tables = extract_markdown_tables(text)
    table_rule = case.get("table", {})
    if table_rule.get("required") and not tables:
        errors.append("Required Markdown table missing from final answer")
    for table in tables:
        if len(table["rows"]) > table_rule.get("max_rows", 15):
            errors.append(
                f"Markdown table exceeds row cap: {len(table['rows'])} > "
                f"{table_rule.get('max_rows', 15)}"
            )
        if len(table["columns"]) > table_rule.get("max_columns", 12):
            errors.append(
                f"Markdown table exceeds column cap: {len(table['columns'])} > "
                f"{table_rule.get('max_columns', 12)}"
            )

    record_ids: list[str] = []
    record_column = table_rule.get("record_id_column")
    if record_column:
        for table in tables:
            for row in table["rows"]:
                if record_column in row:
                    record_ids.append(row[record_column])
        overlap = set(record_ids) & (prior_record_ids or set())
        if overlap:
            errors.append(f"Pagination overlap with prior page: {sorted(overlap)}")
    return {"errors": errors, "tables": tables, "record_ids": record_ids}


def serialize_response(response: Any) -> dict[str, Any]:
    if hasattr(response, "model_dump"):
        return response.model_dump(mode="json")
    if isinstance(response, dict):
        return response
    raise TypeError(f"Unsupported response type: {type(response).__name__}")


def classify_demo_verdict(errors: list[str], manual_scores: list[int]) -> str:
    if errors:
        return "FAIL"
    if not manual_scores:
        return "PENDING"
    percentage = sum(manual_scores) / (2 * len(manual_scores))
    if percentage >= 0.8:
        return "PASS"
    if percentage >= 0.6:
        return "PARTIAL"
    return "FAIL"


def render_demo_report(results: list[dict[str, Any]]) -> str:
    automated_passes = sum(not result.get("errors") for result in results)
    lines = [
        "# Manufacturing Agent Demo Evaluation",
        "",
        f"Automated checks passed: **{automated_passes}/{len(results)}**.",
        "",
    ]
    for result in results:
        verdict = classify_demo_verdict(
            result.get("errors", []), result.get("manual_scores", [])
        )
        lines.extend(
            [
                f"## {result['id']}",
                "",
                f"**Question:** {result.get('question', '')}",
                "",
                f"**Verdict:** {verdict}",
                f"**Code Interpreter:** {'Yes' if result.get('code_interpreter_called') else 'No'}"
                f" ({result.get('code_calls', 0)} calls)",
                f"**Tokens:** {result.get('total_tokens', 'n/a')}",
                f"**Elapsed:** {result.get('elapsed_seconds', 0)} seconds",
                "",
                "### What worked well",
                "",
                result.get("worked_well", "Manual review pending."),
                "",
                "### What went wrong",
                "",
                result.get("went_wrong", "Manual review pending."),
                "",
                "### Incorrect or missing facts",
                "",
                "\n".join(f"- {error}" for error in result.get("errors", []))
                or "- None detected by automated checks.",
                "",
                "### Recommended general prompt improvement",
                "",
                result.get("prompt_improvement", "Manual review pending."),
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def batch_cases(cases: list[dict[str, Any]], size: int = 5) -> list[list[dict[str, Any]]]:
    if size < 1:
        raise ValueError("Batch size must be positive")
    batches: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for case in cases:
        requires_machine_output = bool(case.get("expected_metrics")) or bool(
            case.get("require_evaluation_json")
        )
        if requires_machine_output:
            if current:
                batches.append(current)
                current = []
            batches.append([case])
        else:
            current.append(case)
            if len(current) == size:
                batches.append(current)
                current = []
    if current:
        batches.append(current)
    return batches


def run_with_rate_limit_retry(
    operation: Callable[[], Any],
    sleep: Callable[[float], None] = time.sleep,
    *,
    delay: float = 60,
    attempts: int = 3,
) -> Any:
    for attempt in range(attempts):
        try:
            return operation()
        except Exception as error:
            is_rate_limit = (
                type(error).__name__ == "RateLimitError"
                or getattr(error, "status_code", None) == 429
            )
            # Code Interpreter containers idle out; the service asks for a plain retry.
            is_expired_container = (
                getattr(error, "status_code", None) == 409
                and "container_expired" in str(error)
            )
            is_transient_network = type(error).__name__ in {"APIConnectionError", "APITimeoutError"}
            if not (is_rate_limit or is_expired_container or is_transient_network) or attempt == attempts - 1:
                raise
            sleep(delay if is_rate_limit else 5)
    raise RuntimeError("unreachable")


def load_cases(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError("Evaluation dataset must be a JSON array")
    seen: set[str] = set()
    for case in value:
        for field in ("id", "question", "requires_code_interpreter"):
            if field not in case:
                raise ValueError(f"Evaluation case missing {field!r}")
        if case["id"] in seen:
            raise ValueError(f"Duplicate evaluation case ID: {case['id']}")
        seen.add(case["id"])
    return value


def select_cases(
    cases: list[dict[str, Any]],
    *,
    case_id: str | None = None,
    smoke: bool = False,
    all_cases: bool = False,
) -> list[dict[str, Any]]:
    if sum((case_id is not None, smoke, all_cases)) != 1:
        raise ValueError("Select exactly one of case_id, smoke, or all_cases")
    if case_id is not None:
        selected = [case for case in cases if case["id"] == case_id]
        if not selected:
            raise ValueError(f"Unknown evaluation case: {case_id}")
        return selected
    if smoke:
        return [case for case in cases if case.get("smoke", False)]
    return list(cases)


def _evaluation_payload(text: str) -> dict[str, Any] | None:
    match = EVALUATION_BLOCK.search(text)
    if not match:
        return None
    try:
        value = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def evaluate_response(
    case: dict[str, Any], text: str, code_interpreter_called: bool
) -> list[str]:
    errors: list[str] = []
    if case.get("requires_code_interpreter") and not code_interpreter_called:
        errors.append("Code Interpreter was not invoked")

    lowered = text.casefold()
    for qualifier in case.get("required_qualifiers", []):
        alternatives = qualifier if isinstance(qualifier, list) else [qualifier]
        if not any(str(value).casefold() in lowered for value in alternatives):
            errors.append(f"Required qualifier missing: {qualifier}")
    for claim in case.get("forbidden_claims", []):
        if _claim_asserted(lowered, claim):
            errors.append(f"Forbidden claim present: {claim}")

    strict_payload = bool(case.get("expected_metrics")) or bool(
        case.get("require_evaluation_json")
    )
    payload = _evaluation_payload(text)
    if payload is None:
        if strict_payload:
            errors.append("Missing evaluation_json block")
        return errors

    metrics = payload.get("metrics", {})
    for name, expectation in case.get("expected_metrics", {}).items():
        if name not in metrics:
            errors.append(f"Expected metric missing: {name}")
            continue
        try:
            actual = Decimal(str(metrics[name]))
            expected = Decimal(str(expectation["value"]))
            tolerance = Decimal(str(expectation.get("tolerance", "0")))
        except (InvalidOperation, TypeError, ValueError, KeyError):
            errors.append(f"Metric is not comparable: {name}={metrics[name]!r}")
            continue
        if abs(actual - expected) > tolerance:
            errors.append(f"Metric {name}: expected {expected} ± {tolerance}, got {actual}")

    if strict_payload:
        detail_rows = payload.get("detail_rows", 0)
        maximum = case.get("max_detail_rows", 10)
        if not isinstance(detail_rows, int) or detail_rows < 0 or detail_rows > maximum:
            errors.append(
                f"detail_rows must be an integer from 0 to {maximum}, got {detail_rows!r}"
            )
        if case.get("require_evaluation_json"):
            detail_records = payload.get("detail_records")
            if not isinstance(detail_records, list) or len(detail_records) != detail_rows:
                errors.append(
                    "detail_records must list every displayed detailed record and match detail_rows"
                )
    return errors
