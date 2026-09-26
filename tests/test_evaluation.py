import json
import tempfile
import unittest
from pathlib import Path

from src.evaluation import (
    batch_cases,
    classify_demo_verdict,
    evaluate_demo_response,
    extract_markdown_tables,
    group_demo_cases,
    evaluate_response,
    load_cases,
    load_known_ids,
    render_demo_report,
    run_with_rate_limit_retry,
    select_cases,
    serialize_response,
)
from scripts.evaluate_agent import evaluation_agent_reference, evaluation_prompt


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

    def test_demo_dataset_has_ten_golden_questions_in_two_demo_chats(self):
        cases = load_cases(ROOT / "evaluations/demo_questions.json")

        kinds = [case["kind"] for case in cases]
        self.assertEqual(kinds.count("golden"), 10)
        self.assertGreaterEqual(kinds.count("alternate"), 3)
        self.assertGreaterEqual(kinds.count("variant"), 2)
        self.assertGreaterEqual(kinds.count("metadata"), 4)
        self.assertLessEqual(set(kinds), {"golden", "alternate", "variant", "metadata"})
        golden = [case for case in cases if case["kind"] == "golden"]
        self.assertEqual({case["conversation_group"] for case in golden}, {"demo_1", "demo_2"})
        self.assertEqual({case["tier"] for case in golden}, {"quick", "deep"})
        for case in golden:
            self.assertNotRegex(case["question"], r"_|\bS00\d\b|\bSOL\d|\bWH\d|\.csv", case["id"])

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
        self.assertIn('"detail_records": []', prompt)

    def test_agent_reference_is_pinned_to_recorded_version(self):
        reference = evaluation_agent_reference(
            {"agent_name": "agent", "agent_version": "5"}
        )
        self.assertEqual(
            reference,
            {"name": "agent", "version": "5", "type": "agent_reference"},
        )


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

    def test_retries_expired_code_interpreter_container(self):
        class ConflictError(Exception):
            status_code = 409

        attempts: list[int] = []
        sleeps: list[float] = []

        def operation():
            attempts.append(1)
            if len(attempts) == 1:
                raise ConflictError("Error code: 409 - {'code': 'container_expired'}")
            return "ok"

        result = run_with_rate_limit_retry(operation, sleeps.append, delay=60)

        self.assertEqual(result, "ok")
        self.assertEqual(sleeps, [5])

    def test_retries_transient_connection_errors(self):
        class APIConnectionError(Exception):
            pass

        attempts: list[int] = []
        sleeps: list[float] = []

        def operation():
            attempts.append(1)
            if len(attempts) == 1:
                raise APIConnectionError("Connection error.")
            return "ok"

        self.assertEqual(run_with_rate_limit_retry(operation, sleeps.append, delay=60), "ok")
        self.assertEqual(sleeps, [5])

    def test_does_not_retry_other_conflicts(self):
        class ConflictError(Exception):
            status_code = 409

        def operation():
            raise ConflictError("some other conflict")

        with self.assertRaisesRegex(ConflictError, "other conflict"):
            run_with_rate_limit_retry(operation, lambda _: None)

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

    def test_pagination_counts_machine_readable_detail_records(self):
        case = self.case(
            expected_metrics={}, required_qualifiers=[], require_evaluation_json=True
        )
        text = self.response(
            detail_rows=10,
            detail_records=[f"line-{index}" for index in range(9)],
        )
        errors = evaluate_response(case, text, True)
        self.assertTrue(any("detail_records" in error for error in errors))

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


class DemoEvaluationTests(unittest.TestCase):
    def test_extracts_markdown_table_shape_and_record_ids(self):
        text = """Answer.\n\n| sales_order_line_id | value |\n|---|---:|\n| SOL1 | ₹1,200.00 |\n| SOL2 | ₹900.00 |"""

        tables = extract_markdown_tables(text)

        self.assertEqual(tables[0]["columns"], ["sales_order_line_id", "value"])
        self.assertEqual(len(tables[0]["rows"]), 2)
        self.assertEqual(tables[0]["rows"][0]["sales_order_line_id"], "SOL1")

    def test_requires_table_in_final_answer_and_enforces_caps(self):
        case = {
            "requires_code_interpreter": True,
            "table": {"required": True, "max_rows": 1, "max_columns": 2},
        }
        no_table = evaluate_demo_response(case, "The Python output had a table.", True)
        too_many_rows = evaluate_demo_response(
            case,
            "| id | value |\n|---|---|\n| A | 1 |\n| B | 2 |",
            True,
        )

        self.assertIn("Required Markdown table missing from final answer", no_table["errors"])
        self.assertTrue(any("row cap" in error for error in too_many_rows["errors"]))

    def test_matches_values_despite_business_formatting(self):
        case = {
            "requires_code_interpreter": True,
            "required_values": ["6612240.06", "SOL000213367"],
        }

        result = evaluate_demo_response(
            case,
            "Exposure is ₹6,612,240.06 for SOL000213367.",
            True,
        )

        self.assertEqual(result["errors"], [])

    def test_rejects_page_overlap(self):
        case = {
            "requires_code_interpreter": True,
            "table": {
                "required": True,
                "max_rows": 10,
                "max_columns": 12,
                "record_id_column": "sales_order_line_id",
            },
        }
        text = "| sales_order_line_id |\n|---|\n| SOL1 |\n| SOL2 |"

        result = evaluate_demo_response(
            case, text, True, prior_record_ids={"SOL1"}
        )

        self.assertTrue(any("overlap" in error for error in result["errors"]))
        self.assertEqual(result["record_ids"], ["SOL1", "SOL2"])

    def test_flags_record_ids_that_do_not_exist_in_source_data(self):
        case = {"requires_code_interpreter": True}
        text = "Act on SOL000213367 and SOL000012345 (order SO000001234)."

        result = evaluate_demo_response(
            case, text, True, known_ids={"SOL000213367", "SO000081226"}
        )

        self.assertIn(
            "Unknown record IDs (possible fabrication): SO000001234, SOL000012345",
            result["errors"],
        )

    def test_known_ids_check_is_skipped_without_reference_set(self):
        result = evaluate_demo_response({}, "SOL000012345", False)

        self.assertEqual(result["errors"], [])

    def test_enforces_prose_word_limit_excluding_tables(self):
        case = {"max_words": 5}
        table = "| a | b |\n|---|---|\n" + "| word word word | x |\n" * 5

        within = evaluate_demo_response(case, "One two three four.\n\n" + table, False)
        over = evaluate_demo_response(case, "One two three four five six.", False)

        self.assertEqual(within["errors"], [])
        self.assertIn("Answer too long: 6 words > 5", over["errors"])

    def test_negated_forbidden_claim_is_not_a_claim(self):
        case = {"forbidden_claims": ["live prediction", "hold has been released"]}

        negated = evaluate_demo_response(case, "These are replay scores, not live predictions.", False)
        asserted = evaluate_demo_response(case, "These are live predictions.", False)
        released = evaluate_demo_response(case, "The hold has been released.", False)

        self.assertEqual(negated["errors"], [])
        self.assertIn("Forbidden claim present: live prediction", asserted["errors"])
        self.assertIn("Forbidden claim present: hold has been released", released["errors"])

    def test_rejects_any_snake_case_code_but_not_the_model_name(self):
        flagged = evaluate_demo_response({}, "| Hold |\n|---|\n| credit_limit |", False)
        allowed = evaluate_demo_response({}, "*Scope: replay scores from logistic_regression v1.*", False)

        self.assertTrue(any("credit_limit" in error for error in flagged["errors"]))
        self.assertEqual(allowed["errors"], [])

    def test_rejects_printed_source_tags_in_any_form(self):
        for text in ("Revenue ₹4.84M (printed).", "Revenue ₹4.84M. (Printed: 1406, 1020.)"):
            result = evaluate_demo_response({}, text, False)
            self.assertTrue(any("(printed" in error for error in result["errors"]), text)

    def test_rejects_method_narration_and_raw_column_names(self):
        result = evaluate_demo_response({}, "What I did: filtered operational_queue_status.", False)

        self.assertTrue(any("what i did" in error for error in result["errors"]))
        self.assertTrue(any("operational_queue_status" in error for error in result["errors"]))
        self.assertEqual(
            evaluate_demo_response({"style_checks": False}, "What I did", False)["errors"], []
        )

    def test_loads_known_ids_from_sales_csv(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fact_sales.csv"
            path.write_text(
                "sales_order_line_id,sales_order_id,x\nSOL000000001,SO000000001,1\n",
                encoding="utf-8",
            )

            self.assertEqual(load_known_ids(path), {"SOL000000001", "SO000000001"})

    def test_serializes_response_without_losing_tool_output(self):
        class Response:
            def model_dump(self, **_kwargs):
                return {
                    "id": "resp-1",
                    "output": [{"type": "code_interpreter_call", "code": "print(1)"}],
                }

        payload = serialize_response(Response())

        self.assertEqual(payload["output"][0]["type"], "code_interpreter_call")
        self.assertEqual(payload["output"][0]["code"], "print(1)")

    def test_verdict_thresholds_and_report_sections(self):
        self.assertEqual(classify_demo_verdict(["hard failure"], [2, 2]), "FAIL")
        self.assertEqual(classify_demo_verdict([], [2, 2, 2, 2, 2]), "PASS")
        self.assertEqual(classify_demo_verdict([], [1, 1, 1, 2, 2]), "PARTIAL")

        report = render_demo_report(
            [{
                "id": "q1",
                "question": "Question?",
                "errors": [],
                "code_interpreter_called": True,
                "elapsed_seconds": 1.2,
            }]
        )
        self.assertIn("## q1", report)
        self.assertIn("What worked well", report)
        self.assertIn("What went wrong", report)
        self.assertIn("Manual review pending", report)


if __name__ == "__main__":
    unittest.main()
