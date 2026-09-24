import json
import tempfile
import unittest
from pathlib import Path

from src.evaluation import (
    batch_cases,
    evaluate_response,
    load_cases,
    run_with_rate_limit_retry,
    select_cases,
)
from scripts.evaluate_agent import evaluation_prompt


ROOT = Path(__file__).resolve().parents[1]


class LoadCasesTests(unittest.TestCase):
    def write_cases(self, path: Path, cases: list[dict]) -> None:
        path.write_text(json.dumps(cases), encoding="utf-8")

    def test_loads_unique_cases(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cases.json"
            self.write_cases(path, [{"id": "one", "question": "Q", "requires_code_interpreter": True}])
            self.assertEqual(load_cases(path)[0]["id"], "one")

    def test_rejects_duplicate_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cases.json"
            case = {"id": "one", "question": "Q", "requires_code_interpreter": True}
            self.write_cases(path, [case, case])
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                load_cases(path)

    def test_repository_dataset_has_18_cases_and_five_smoke_cases(self):
        cases = load_cases(ROOT / "evaluations/golden_questions.json")
        self.assertEqual(len(cases), 18)
        self.assertEqual(sum(case.get("smoke", False) for case in cases), 5)

    def test_inventory_oracle_defines_its_population_and_status_formula(self):
        cases = load_cases(ROOT / "evaluations/golden_questions.json")
        question = next(
            case["question"] for case in cases if case["id"] == "inventory_snapshot"
        )

        self.assertIn("every row in fact_inventory_lots.csv", question)
        self.assertIn("quality_status != 'released'", question)

    def test_finance_oracle_defines_total_and_overdue_populations(self):
        cases = load_cases(ROOT / "evaluations/golden_questions.json")
        question = next(
            case["question"] for case in cases if case["id"] == "overdue_finance"
        )

        self.assertIn("every row in fact_finance.csv", question)
        self.assertIn("(due_date < '2026-09-15') & (outstanding_amount > 0)", question)
        self.assertIn("not calculated_outstanding_amount", question)

    def test_pune_oracle_defines_active_statuses_and_warehouse_key(self):
        cases = load_cases(ROOT / "evaluations/golden_questions.json")
        question = next(
            case["question"] for case in cases if case["id"] == "pune_commitments_due_7d"
        )

        self.assertIn("open, on_hold, or partially_shipped", question)
        self.assertIn("warehouse_key 2", question)

    def test_quality_case_requests_an_explicit_causation_limitation(self):
        cases = load_cases(ROOT / "evaluations/golden_questions.json")
        case = next(case for case in cases if case["id"] == "quality_signals")

        self.assertIn("causation is not confirmed", case["question"])
        self.assertIn("not confirmed", case["required_qualifiers"][0])


class SelectCasesTests(unittest.TestCase):
    def setUp(self):
        self.cases = [
            {"id": "one", "smoke": True},
            {"id": "two", "smoke": False},
        ]

    def test_selects_one_case(self):
        self.assertEqual(select_cases(self.cases, case_id="two"), [self.cases[1]])

    def test_selects_smoke_cases(self):
        self.assertEqual(select_cases(self.cases, smoke=True), [self.cases[0]])

    def test_selects_all_cases(self):
        self.assertEqual(select_cases(self.cases, all_cases=True), self.cases)

    def test_unknown_case_fails(self):
        with self.assertRaisesRegex(ValueError, "missing"):
            select_cases(self.cases, case_id="missing")


class EvaluationPromptTests(unittest.TestCase):
    def test_preserves_calculated_precision_in_machine_readable_metrics(self):
        prompt = evaluation_prompt(
            {"question": "Q", "expected_metrics": {"amount": {"value": "1.2345"}}}
        )
        self.assertIn("Do not round", prompt)

    def test_detail_rows_excludes_aggregated_groups(self):
        prompt = evaluation_prompt({"question": "Q", "expected_metrics": {}})
        self.assertIn("Do not count aggregated or grouped rows", prompt)

    def test_requires_json_literals_in_a_labelled_template(self):
        prompt = evaluation_prompt({"question": "Q", "expected_metrics": {}})
        self.assertIn("```evaluation_json", prompt)
        self.assertIn("never Python expressions", prompt)


class BatchCasesTests(unittest.TestCase):
    def test_isolates_machine_output_cases_and_batches_qualitative_cases(self):
        cases = [
            {"id": "metric", "expected_metrics": {"count": {"value": "1"}}},
            {"id": "q1", "expected_metrics": {}},
            {"id": "q2", "expected_metrics": {}},
            {"id": "page", "expected_metrics": {}, "require_evaluation_json": True},
            {"id": "q3", "expected_metrics": {}},
        ]

        batches = batch_cases(cases)

        self.assertEqual([[case["id"] for case in batch] for batch in batches], [
            ["metric"], ["q1", "q2"], ["page"], ["q3"]
        ])
        self.assertEqual([case for batch in batches for case in batch], cases)


class RateLimitRetryTests(unittest.TestCase):
    def test_retries_rate_limit_and_returns_result(self):
        class RateLimitError(Exception):
            pass

        attempts: list[int] = []
        sleeps: list[float] = []

        def operation():
            attempts.append(1)
            if len(attempts) == 1:
                raise RateLimitError("slow down")
            return "ok"

        result = run_with_rate_limit_retry(operation, sleeps.append, delay=5)

        self.assertEqual(result, "ok")
        self.assertEqual(len(attempts), 2)
        self.assertEqual(sleeps, [5])

    def test_does_not_retry_non_rate_limit_error(self):
        attempts: list[int] = []

        def operation():
            attempts.append(1)
            raise ValueError("bad request")

        with self.assertRaisesRegex(ValueError, "bad request"):
            run_with_rate_limit_retry(operation, lambda _: None)
        self.assertEqual(len(attempts), 1)


class EvaluateResponseTests(unittest.TestCase):
    def case(self, **overrides):
        value = {
            "id": "case",
            "requires_code_interpreter": True,
            "expected_metrics": {
                "count": {"value": "10", "tolerance": "0"},
                "amount": {"value": "12.30", "tolerance": "0.01"},
            },
            "required_qualifiers": ["partial"],
            "forbidden_claims": ["confirmed cause"],
            "max_detail_rows": 10,
        }
        value.update(overrides)
        return value

    def response(self, **overrides):
        value = {
            "metrics": {"count": 10, "amount": 12.301},
            "detail_rows": 4,
        }
        value.update(overrides)
        return "September is partial.\n```evaluation_json\n" + json.dumps(value) + "\n```"

    def test_accepts_grounded_response_within_tolerance(self):
        self.assertEqual(evaluate_response(self.case(), self.response(), True), [])

    def test_rejects_missing_tool_call(self):
        errors = evaluate_response(self.case(), self.response(), False)
        self.assertIn("Code Interpreter was not invoked", errors)

    def test_rejects_wrong_or_missing_metrics(self):
        errors = evaluate_response(
            self.case(), self.response(metrics={"count": 9}), True
        )
        self.assertTrue(any("count" in error for error in errors))
        self.assertTrue(any("amount" in error for error in errors))

    def test_rejects_missing_qualifier_and_forbidden_claim(self):
        text = self.response().replace("September is partial.", "This is a confirmed cause.")
        errors = evaluate_response(self.case(), text, True)
        self.assertTrue(any("qualifier" in error for error in errors))
        self.assertTrue(any("Forbidden" in error for error in errors))

    def test_rejects_detail_row_overflow(self):
        errors = evaluate_response(self.case(), self.response(detail_rows=11), True)
        self.assertTrue(any("detail_rows" in error for error in errors))

    def test_limitation_case_does_not_require_code_interpreter(self):
        case = self.case(
            requires_code_interpreter=False,
            expected_metrics={},
            required_qualifiers=["not available"],
        )
        text = self.response(metrics={}).replace("September is partial.", "Predictions are not available.")
        self.assertEqual(evaluate_response(case, text, False), [])

    def test_qualitative_case_allows_missing_evaluation_block(self):
        case = self.case(expected_metrics={}, required_qualifiers=[])
        self.assertEqual(evaluate_response(case, "Grounded qualitative answer.", True), [])

    def test_explicit_pagination_case_still_requires_evaluation_block(self):
        case = self.case(
            expected_metrics={}, required_qualifiers=[], require_evaluation_json=True
        )
        errors = evaluate_response(case, "Ten detailed rows.", True)
        self.assertIn("Missing evaluation_json block", errors)

    def test_malformed_optional_block_does_not_crash_qualitative_case(self):
        case = self.case(expected_metrics={}, required_qualifiers=[])
        text = "```evaluation_json\n{\"metrics\": {\"count\": value}}\n```"
        self.assertEqual(evaluate_response(case, text, True), [])

    def test_qualifier_group_accepts_any_supported_wording(self):
        case = self.case(
            expected_metrics={},
            required_qualifiers=[["cannot", "not confirmed", "no direct link"]],
        )
        self.assertEqual(
            evaluate_response(case, "There is no direct link to customer orders.", True),
            [],
        )

    def test_optional_qualitative_trailer_does_not_apply_detail_cap(self):
        case = self.case(expected_metrics={}, required_qualifiers=[])
        self.assertEqual(evaluate_response(case, self.response(detail_rows=15), True), [])


if __name__ == "__main__":
    unittest.main()
