"""Small deterministic checks for the manufacturing golden questions."""

from __future__ import annotations

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
            if not is_rate_limit or attempt == attempts - 1:
                raise
            sleep(delay)
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
        if claim.casefold() in lowered:
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
