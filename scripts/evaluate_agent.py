"""Run the lightweight manufacturing-agent golden evaluation."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from scripts.create_agent import STATE_PATH, load_state, required_config
from src.evaluation import (
    batch_cases,
    evaluate_response,
    load_cases,
    run_with_rate_limit_retry,
    select_cases,
)


CASES_PATH = ROOT / "evaluations/golden_questions.json"
RESULTS_PATH = ROOT / ".foundry/evaluation-results.json"


def evaluation_prompt(case: dict) -> str:
    metric_names = list(case.get("expected_metrics", {}))
    template = json.dumps(
        {"metrics": {name: 0 for name in metric_names}, "detail_rows": 0}
    )
    return (
        case["question"]
        + "\n\nAutomated evaluation requirement: answer the business question normally, "
        "then finish with this exact structure:\n```evaluation_json\n"
        + template
        + "\n```\nReplace metric zeros with calculated numeric JSON literals"
        + (f" containing these exact numeric keys: {', '.join(metric_names)}" if metric_names else "")
        + "; never Python expressions, variable names, or code. Do not round calculated "
        "metric values in evaluation_json; preserve the "
        "source precision. detail_rows is the number of detailed records shown in the answer. "
        "Do not count aggregated or grouped rows as detail_rows. "
        "Do not put other text after that block."
    )


def main() -> int:
    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential
    from dotenv import load_dotenv

    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--case")
    group.add_argument("--smoke", action="store_true")
    group.add_argument("--all", action="store_true")
    args = parser.parse_args()

    load_dotenv()
    config = required_config(os.environ)
    state = load_state(STATE_PATH)
    if state is None:
        print("FAIL: no recorded persistent deployment; run create_agent.py deploy")
        return 1

    cases = select_cases(
        load_cases(CASES_PATH),
        case_id=args.case,
        smoke=args.smoke,
        all_cases=args.all,
    )
    results: list[dict] = []

    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(
            endpoint=config["project_endpoint"], credential=credential
        ) as project,
        project.get_openai_client() as openai,
    ):
        for batch in batch_cases(cases):
            conversation = openai.conversations.create()
            for case in batch:
                try:
                    response = run_with_rate_limit_retry(
                        lambda: openai.responses.create(
                            conversation=conversation.id,
                            input=evaluation_prompt(case),
                            extra_body={
                                "agent_reference": {
                                    "name": state["agent_name"],
                                    "type": "agent_reference",
                                }
                            },
                        )
                    )
                    tool_called = any(
                        getattr(item, "type", None) == "code_interpreter_call"
                        for item in response.output
                    )
                    errors = evaluate_response(case, response.output_text, tool_called)
                except Exception as error:
                    errors = [f"{type(error).__name__}: {error}"]
                status = "PASS" if not errors else "FAIL"
                print(f"{status}: {case['id']}")
                for error in errors:
                    print(f"  - {error}")
                results.append({"id": case["id"], "status": status, "errors": errors})
                if case is not cases[-1]:
                    time.sleep(5)

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    passed = sum(result["status"] == "PASS" for result in results)
    print(f"Result: {passed}/{len(results)} passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
