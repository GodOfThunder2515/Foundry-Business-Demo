"""Run the ten-question manufacturing demo evaluation with visible traces."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from scripts.create_agent import GOLD_CSV_DIR, load_state, required_config, state_path
from src.evaluation import (
    evaluate_demo_response,
    group_demo_cases,
    load_cases,
    load_known_ids,
    render_demo_report,
    run_with_rate_limit_retry,
    serialize_response,
)


CASES_PATH = ROOT / "evaluations/demo_questions.json"
RUNS_ROOT = ROOT / ".foundry/demo-evaluation"
SALES_CSV = GOLD_CSV_DIR / "fact_sales.csv"
DATA_NOT_LOADED_REPLY = "didn't load fully in this session"


def select_demo_cases(
    cases: list[dict[str, Any]],
    *,
    question_id: str | None = None,
    group_id: str | None = None,
    all_cases: bool = False,
) -> list[dict[str, Any]]:
    if sum((question_id is not None, group_id is not None, all_cases)) != 1:
        raise ValueError("Select exactly one question, group, or --all")
    if question_id is not None:
        selected = [case for case in cases if case["id"] == question_id]
    elif group_id is not None:
        selected = [case for case in cases if case["conversation_group"] == group_id]
    else:
        return list(cases)
    if not selected:
        raise ValueError(f"Unknown demo selection: {question_id or group_id}")
    return selected


def _code_calls(response: Any) -> int:
    return sum(
        (
            item.get("type") if isinstance(item, dict) else getattr(item, "type", None)
        )
        == "code_interpreter_call"
        for item in response.output
    )


def sandbox_data_loaded(trace: dict[str, Any]) -> bool:
    """False if a Code Interpreter output reports the setup's DATA_NOT_LOADED check.

    Only tool outputs are searched: the response also echoes the instructions,
    which mention the marker.
    """
    for item in trace.get("output", []):
        if item.get("type") != "code_interpreter_call":
            continue
        for output in item.get("outputs") or []:
            if "DATA_NOT_LOADED" in (output.get("logs") or ""):
                return False
    return True


def _total_tokens(response: Any) -> int | None:
    usage = getattr(response, "usage", None)
    return getattr(usage, "total_tokens", None)


def run_demo_evaluation(
    cases: list[dict[str, Any]],
    *,
    create_conversation: Callable[[], str],
    invoke: Callable[[str, str], Any],
    metadata: dict[str, Any],
    known_ids: set[str] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    records_by_case: dict[str, set[str]] = {}
    case_count = 0
    for group_name, group in group_demo_cases(cases):
        conversation_id = create_conversation()
        for case in group:
            case_count += 1
            started = time.perf_counter()
            try:
                response = invoke(conversation_id, case["question"])
                code_calls = _code_calls(response)
                tool_called = code_calls > 0
                prior_ids = records_by_case.get(case.get("pagination_from", ""), set())
                evaluation = evaluate_demo_response(
                    case,
                    response.output_text,
                    tool_called,
                    prior_record_ids=prior_ids,
                    known_ids=known_ids,
                )
                records_by_case[case["id"]] = set(evaluation["record_ids"])
                trace = serialize_response(response)
                # The agent may give the fallback reply without running the check that raises.
                data_loaded = sandbox_data_loaded(trace) and (
                    DATA_NOT_LOADED_REPLY not in response.output_text
                )
                if not data_loaded:
                    evaluation["errors"].insert(0, "Sandbox data not fully loaded (DATA_NOT_LOADED)")
                result = {
                    **metadata,
                    "id": case["id"],
                    "question": case["question"],
                    "conversation_group": group_name,
                    "conversation_id": conversation_id,
                    "response_id": response.id,
                    "code_interpreter_called": tool_called,
                    "code_calls": code_calls,
                    "total_tokens": _total_tokens(response),
                    "data_loaded": data_loaded,
                    "elapsed_seconds": round(time.perf_counter() - started, 3),
                    "errors": evaluation["errors"],
                    "table_count": len(evaluation["tables"]),
                    "record_ids": evaluation["record_ids"],
                    "final_answer": response.output_text,
                    "trace": trace,
                }
            except Exception as error:
                result = {
                    **metadata,
                    "id": case["id"],
                    "question": case["question"],
                    "conversation_group": group_name,
                    "conversation_id": conversation_id,
                    "response_id": None,
                    "code_interpreter_called": False,
                    "code_calls": 0,
                    "total_tokens": None,
                    "elapsed_seconds": round(time.perf_counter() - started, 3),
                    "errors": [f"{type(error).__name__}: {error}"],
                    "table_count": 0,
                    "record_ids": [],
                    "final_answer": "",
                    "trace": {"error": f"{type(error).__name__}: {error}"},
                }
            results.append(result)
            if case_count < len(cases):
                sleep(5)
    return results


def write_demo_artifacts(
    run_dir: Path, results: list[dict[str, Any]], metadata: dict[str, Any]
) -> None:
    trace_dir = run_dir / "traces"
    answer_dir = run_dir / "answers"
    trace_dir.mkdir(parents=True, exist_ok=True)
    answer_dir.mkdir(parents=True, exist_ok=True)
    for result in results:
        trace_payload = {
            "question": result["question"],
            "conversation_group": result["conversation_group"],
            "conversation_id": result["conversation_id"],
            "response_id": result["response_id"],
            "response": result["trace"],
        }
        (trace_dir / f"{result['id']}.json").write_text(
            json.dumps(trace_payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        (answer_dir / f"{result['id']}.md").write_text(
            result["final_answer"].rstrip() + "\n", encoding="utf-8"
        )
    summaries = [
        {key: value for key, value in result.items() if key not in {"trace", "final_answer"}}
        for result in results
    ]
    (run_dir / "run.json").write_text(
        json.dumps({"metadata": metadata, "results": summaries}, indent=2) + "\n",
        encoding="utf-8",
    )
    (run_dir / "report.md").write_text(
        render_demo_report(results), encoding="utf-8"
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--question")
    selection.add_argument("--group")
    selection.add_argument("--all", action="store_true")
    parser.add_argument(
        "--cases", type=Path, default=CASES_PATH, help="case file (default: demo_questions.json)"
    )
    return parser.parse_args(argv)


def main() -> int:
    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential
    from dotenv import load_dotenv

    args = parse_args()

    load_dotenv()
    config = required_config(os.environ)
    state = load_state(state_path(os.environ))
    if state is None:
        print("FAIL: no recorded persistent deployment; run create_agent.py deploy")
        return 1

    cases = select_demo_cases(
        load_cases(args.cases),
        question_id=args.question,
        group_id=args.group,
        all_cases=args.all,
    )
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = RUNS_ROOT / run_id
    metadata = {
        "run_id": run_id,
        "cases_file": args.cases.name,
        "agent_name": state["agent_name"],
        "agent_version": state["agent_version"],
        "model": config["model_deployment"],
        "reasoning_effort": state.get("reasoning_effort"),
        "snapshot_id": state.get("snapshot_id"),
        "data_as_of": "2026-09-15",
    }
    agent_reference = {
        "name": state["agent_name"],
        "version": state["agent_version"],
        "type": "agent_reference",
    }

    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(
            endpoint=config["project_endpoint"], credential=credential
        ) as project,
        project.get_openai_client() as openai,
    ):
        results = run_demo_evaluation(
            cases,
            create_conversation=lambda: openai.conversations.create().id,
            invoke=lambda conversation_id, question: run_with_rate_limit_retry(
                lambda: openai.responses.create(
                    conversation=conversation_id,
                    input=question,
                    include=["code_interpreter_call.outputs"],
                    extra_body={"agent_reference": agent_reference},
                )
            ),
            metadata=metadata,
            known_ids=load_known_ids(SALES_CSV),
        )

    write_demo_artifacts(run_dir, results, metadata)
    for result in results:
        status = "PASS" if not result["errors"] else "FAIL"
        print(f"{status}: {result['id']} ({result['elapsed_seconds']}s)")
        for error in result["errors"]:
            print(f"  - {error}")
    passed = sum(not result["errors"] for result in results)
    print(f"Automated result: {passed}/{len(results)} passed")
    print(f"Artifacts: {run_dir}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
