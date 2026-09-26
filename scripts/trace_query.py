"""Ask the deployed agent one question and save the full trace, including sandbox outputs.

Usage:
  .venv\\Scripts\\python.exe scripts\\trace_query.py "Which commitments are most at risk?"
  .venv\\Scripts\\python.exe scripts\\trace_query.py "Show the next 10." --conversation conv_...
  .venv\\Scripts\\python.exe scripts\\trace_query.py "..." --version 9
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from scripts.create_agent import load_state, required_config, state_path
from src.evaluation import run_with_rate_limit_retry


TRACE_DIR = ROOT / ".foundry/traces"


def summarize_trace(trace: dict[str, Any], output_chars: int = 1500) -> str:
    """Render code, sandbox output and the final answer as a readable timeline."""
    code_calls = [item for item in trace["output"] if item["type"] == "code_interpreter_call"]
    usage = trace.get("usage") or {}
    lines = [
        f"response: {trace['id']}",
        f"conversation: {(trace.get('conversation') or {}).get('id')}",
        f"elapsed: {trace.get('_client_elapsed_s')} s | code calls: {len(code_calls)} | "
        f"tokens: {usage.get('total_tokens')} (reasoning "
        f"{(usage.get('output_tokens_details') or {}).get('reasoning_tokens')})",
    ]
    for index, item in enumerate(trace["output"]):
        if item["type"] == "code_interpreter_call":
            lines += ["", f"=== [{index}] CODE", item.get("code") or ""]
            for output in item.get("outputs") or []:
                text = output.get("logs") or json.dumps(output)
                clipped = text if len(text) <= output_chars else text[:output_chars] + " …[clipped]"
                lines += [f"=== [{index}] OUTPUT", clipped]
        elif item["type"] == "message":
            answer = "".join(part.get("text", "") for part in item["content"])
            lines += ["", f"=== [{index}] FINAL ANSWER", answer]
    return "\n".join(lines)


def main() -> int:
    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential
    from dotenv import load_dotenv

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question")
    parser.add_argument("--conversation", help="continue an existing conversation")
    parser.add_argument("--version", help="agent version (default: recorded deployment)")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    config = required_config(os.environ)
    state = load_state(state_path(os.environ)) or {}
    version = args.version or state.get("agent_version")
    if not version:
        print("FAIL: no --version given and no recorded deployment")
        return 1

    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(endpoint=config["project_endpoint"], credential=credential) as project,
        project.get_openai_client() as openai,
    ):
        conversation = args.conversation or openai.conversations.create().id
        started = time.perf_counter()
        response = run_with_rate_limit_retry(
            lambda: openai.responses.create(
                conversation=conversation,
                input=args.question,
                include=["code_interpreter_call.outputs"],
                extra_body={
                    "agent_reference": {
                        "type": "agent_reference",
                        "name": config["agent_name"],
                        "version": version,
                    }
                },
            )
        )
        trace = response.model_dump(mode="json")
        trace["_client_elapsed_s"] = round(time.perf_counter() - started, 1)

    TRACE_DIR.mkdir(parents=True, exist_ok=True)
    path = TRACE_DIR / f"{trace['id']}.json"
    path.write_text(json.dumps(trace, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(summarize_trace(trace))
    print(f"\nSaved: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
