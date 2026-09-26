import json
import tempfile
import unittest
from pathlib import Path

from scripts.evaluate_demo import (
    CASES_PATH,
    parse_args,
    run_demo_evaluation,
    select_demo_cases,
    write_demo_artifacts,
)
from scripts.trace_query import summarize_trace
from src.evaluation import load_cases


class FakeItem:
    type = "code_interpreter_call"


class FakeResponse:
    def __init__(self, response_id: str, text: str):
        self.id = response_id
        self.output_text = text
        self.output = [FakeItem()]

    def model_dump(self, **_kwargs):
        return {
            "id": self.id,
            "output": [{"type": "code_interpreter_call", "code": "print(1)"}],
            "output_text": self.output_text,
        }


class DemoRunnerTests(unittest.TestCase):
    def cases(self):
        return [
            {
                "id": "a1",
                "conversation_group": "A",
                "question": "First natural question?",
                "requires_code_interpreter": True,
            },
            {
                "id": "a2",
                "conversation_group": "A",
                "question": "Follow-up?",
                "requires_code_interpreter": True,
            },
            {
                "id": "b1",
                "conversation_group": "B",
                "question": "Fresh question?",
                "requires_code_interpreter": True,
            },
        ]

    def test_cases_file_defaults_to_demo_questions_and_can_be_overridden(self):
        self.assertEqual(parse_args(["--all"]).cases, CASES_PATH)
        args = parse_args(["--all", "--cases", "evaluations/demo_candidates.json"])
        self.assertEqual(args.cases.name, "demo_candidates.json")

    def test_candidate_file_has_fifteen_natural_questions_in_two_tiers(self):
        cases = load_cases(CASES_PATH.with_name("demo_candidates.json"))

        self.assertEqual(len(cases), 15)
        self.assertEqual({case["tier"] for case in cases}, {"quick", "deep"})
        for case in cases:
            self.assertNotRegex(case["question"], r"_|\bS00\d\b|\bSOL\d|\bWH\d|\.csv", case["id"])

    def test_selects_one_question_or_one_group(self):
        cases = self.cases()
        self.assertEqual(select_demo_cases(cases, question_id="a2")[0]["id"], "a2")
        self.assertEqual(
            [case["id"] for case in select_demo_cases(cases, group_id="A")],
            ["a1", "a2"],
        )

    def test_reuses_conversation_within_group_and_sends_natural_questions(self):
        conversations = iter(["conv-a", "conv-b"])
        invocations = []

        def invoke(conversation_id, question):
            invocations.append((conversation_id, question))
            return FakeResponse(f"resp-{len(invocations)}", "Grounded answer")

        results = run_demo_evaluation(
            self.cases(),
            create_conversation=lambda: next(conversations),
            invoke=invoke,
            metadata={"agent_version": "8"},
            sleep=lambda _seconds: None,
        )

        self.assertEqual(
            [conversation for conversation, _question in invocations],
            ["conv-a", "conv-a", "conv-b"],
        )
        self.assertEqual(invocations[0][1], "First natural question?")
        self.assertNotIn("evaluation_json", invocations[0][1])
        self.assertTrue(all(result["code_interpreter_called"] for result in results))

    def test_counts_code_calls_and_checks_ids_against_known_set(self):
        class TwoCallResponse(FakeResponse):
            def __init__(self):
                super().__init__("resp-1", "Top line SOL000099999.")
                self.output = [FakeItem(), FakeItem()]

        results = run_demo_evaluation(
            self.cases()[:1],
            create_conversation=lambda: "conv-a",
            invoke=lambda _conversation, _question: TwoCallResponse(),
            metadata={},
            known_ids={"SOL000000001"},
            sleep=lambda _seconds: None,
        )

        self.assertEqual(results[0]["code_calls"], 2)
        self.assertTrue(any("SOL000099999" in error for error in results[0]["errors"]))

    def test_flags_sessions_where_data_did_not_fully_load(self):
        class PartialMountResponse(FakeResponse):
            def model_dump(self, **_kwargs):
                return {
                    "id": self.id,
                    "output": [{
                        "type": "code_interpreter_call",
                        "outputs": [{"type": "logs", "logs": "RuntimeError: DATA_NOT_LOADED: 9 of 19 files mounted"}],
                    }],
                }

        results = run_demo_evaluation(
            self.cases()[:1],
            create_conversation=lambda: "conv-a",
            invoke=lambda _conversation, _question: PartialMountResponse("resp-1", "Please start a new chat."),
            metadata={},
            sleep=lambda _seconds: None,
        )

        self.assertIn("Sandbox data not fully loaded (DATA_NOT_LOADED)", results[0]["errors"])
        self.assertFalse(results[0]["data_loaded"])

    def test_fallback_reply_counts_as_failed_load_even_without_marker(self):
        reply = (
            "The data didn't load fully in this session, so I can't give a reliable answer. "
            "Please start a new chat and ask again."
        )
        results = run_demo_evaluation(
            self.cases()[:1],
            create_conversation=lambda: "conv-a",
            invoke=lambda _conversation, _question: FakeResponse("resp-1", reply),
            metadata={},
            sleep=lambda _seconds: None,
        )

        self.assertFalse(results[0]["data_loaded"])
        self.assertIn("Sandbox data not fully loaded (DATA_NOT_LOADED)", results[0]["errors"])

    def test_marker_in_instructions_does_not_count_as_failed_load(self):
        class InstructionsResponse(FakeResponse):
            def model_dump(self, **_kwargs):
                return {
                    "id": self.id,
                    "instructions": "If the setup raises DATA_NOT_LOADED, stop.",
                    "output": [{"type": "code_interpreter_call", "outputs": [{"type": "logs", "logs": "ok"}]}],
                }

        results = run_demo_evaluation(
            self.cases()[:1],
            create_conversation=lambda: "conv-a",
            invoke=lambda _conversation, _question: InstructionsResponse("resp-1", "Answer"),
            metadata={},
            sleep=lambda _seconds: None,
        )

        self.assertTrue(results[0]["data_loaded"])
        self.assertEqual(results[0]["errors"], [])

    def test_records_failure_and_continues(self):
        calls = []

        def invoke(_conversation_id, question):
            calls.append(question)
            if len(calls) == 1:
                raise ValueError("broken")
            return FakeResponse("resp-ok", "Answer")

        results = run_demo_evaluation(
            self.cases()[:2],
            create_conversation=lambda: "conv-a",
            invoke=invoke,
            metadata={},
            sleep=lambda _seconds: None,
        )

        self.assertEqual(len(calls), 2)
        self.assertIn("ValueError: broken", results[0]["errors"])
        self.assertEqual(results[1]["response_id"], "resp-ok")

    def test_writes_trace_answer_run_and_report(self):
        result = {
            "id": "a1",
            "question": "Question?",
            "conversation_group": "A",
            "conversation_id": "conv-a",
            "response_id": "resp-a",
            "code_interpreter_called": True,
            "elapsed_seconds": 1.0,
            "errors": [],
            "final_answer": "Final answer",
            "trace": {"output": [{"type": "code_interpreter_call"}]},
        }
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            write_demo_artifacts(run_dir, [result], {"agent_version": "8"})

            self.assertEqual((run_dir / "answers/a1.md").read_text(), "Final answer\n")
            trace = json.loads((run_dir / "traces/a1.json").read_text())
            self.assertEqual(trace["response"]["output"][0]["type"], "code_interpreter_call")
            self.assertTrue((run_dir / "run.json").is_file())
            self.assertIn("## a1", (run_dir / "report.md").read_text())


class TraceSummaryTests(unittest.TestCase):
    def test_summarizes_code_outputs_and_answer(self):
        trace = {
            "id": "resp-1",
            "conversation": {"id": "conv-1"},
            "_client_elapsed_s": 12.5,
            "usage": {"total_tokens": 900, "output_tokens_details": {"reasoning_tokens": 300}},
            "output": [
                {"type": "reasoning"},
                {"type": "code_interpreter_call", "code": "print(1)", "outputs": [{"type": "logs", "logs": "x" * 20}]},
                {"type": "message", "content": [{"type": "output_text", "text": "Final."}]},
            ],
        }

        text = summarize_trace(trace, output_chars=10)

        self.assertIn("code calls: 1 | tokens: 900 (reasoning 300)", text)
        self.assertIn("print(1)", text)
        self.assertIn("xxxxxxxxxx …[clipped]", text)
        self.assertIn("=== [2] FINAL ANSWER\nFinal.", text)


if __name__ == "__main__":
    unittest.main()
