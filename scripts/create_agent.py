"""Deploy or clean up the persistent manufacturing prompt agent."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from src.agent_assets import collect_upload_paths, compose_instructions


GOLD_CSV_DIR = (
    ROOT
    / "data/gold_snapshots/epic_soca_6rn73kkx4n/named-outputs/snapshot/csv"
)
PREDICTION_DIR = ROOT / "data/predictions"
HELPER_PATH = ROOT / "src/analysis_helper.py"
CATALOG_PATH = ROOT / "knowledge/dataset_catalog.json"
KNOWLEDGE_DIR = ROOT / "knowledge"
INSTRUCTIONS_PATH = ROOT / "src/agent_instructions.md"
STATE_PATH = ROOT / ".foundry/manufacturing-agent-state.json"
APPROVED_MODEL = "gpt-4.1-mini"


def required_config(environ: Mapping[str, str]) -> dict[str, str]:
    names = (
        "FOUNDRY_PROJECT_ENDPOINT",
        "FOUNDRY_MODEL_DEPLOYMENT",
        "FOUNDRY_AGENT_NAME",
    )
    missing = [name for name in names if not environ.get(name, "").strip()]
    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
    if environ["FOUNDRY_MODEL_DEPLOYMENT"] != APPROVED_MODEL:
        raise ValueError(
            f"FOUNDRY_MODEL_DEPLOYMENT must be {APPROVED_MODEL!r} for this demo"
        )
    return {
        "project_endpoint": environ["FOUNDRY_PROJECT_ENDPOINT"],
        "model_deployment": environ["FOUNDRY_MODEL_DEPLOYMENT"],
        "agent_name": environ["FOUNDRY_AGENT_NAME"],
    }


def prompt_agent_options(
    model: str, instructions: str, tools: Sequence[Any]
) -> dict[str, Any]:
    return {
        "model": model,
        "instructions": instructions,
        "tools": list(tools),
        "temperature": 0,
    }


def load_state(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Deployment state must be a JSON object: {path}")
    return value


def save_state(path: Path, state: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def provision_resources(
    openai: Any,
    upload_paths: Sequence[Path],
    create_agent: Callable[[list[str]], Any],
) -> tuple[Any, list[str]]:
    file_ids: list[str] = []
    try:
        for path in upload_paths:
            with path.open("rb") as handle:
                uploaded = openai.files.create(purpose="assistants", file=handle)
            file_ids.append(uploaded.id)
        return create_agent(file_ids), file_ids
    except Exception:
        for file_id in file_ids:
            try:
                openai.files.delete(file_id)
            except Exception:
                pass
        raise


def cleanup_recorded_resources(
    project: Any, openai: Any, state: Mapping[str, Any]
) -> None:
    failures: list[str] = []
    try:
        project.agents.delete_version(
            agent_name=state["agent_name"],
            agent_version=state["agent_version"],
        )
    except Exception as error:
        if getattr(error, "status_code", None) != 404:
            failures.append(str(error))
    for file_id in state["file_ids"]:
        try:
            openai.files.delete(file_id)
        except Exception as error:
            if getattr(error, "status_code", None) != 404:
                failures.append(str(error))
    if failures:
        raise RuntimeError("; ".join(failures))


def finalize_deployment(
    project: Any,
    openai: Any,
    new_state: Mapping[str, Any],
    *,
    previous: Mapping[str, Any] | None,
    state_path: Path,
    save: Callable[[Path, Mapping[str, Any]], None] = save_state,
) -> None:
    try:
        if previous is not None:
            cleanup_recorded_resources(project, openai, previous)
        save(state_path, new_state)
    except Exception as error:
        try:
            cleanup_recorded_resources(project, openai, new_state)
        except Exception as rollback_error:
            raise RuntimeError(f"{error}; rollback failed: {rollback_error}") from error
        raise


def _clients(config: Mapping[str, str]):
    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential

    credential = DefaultAzureCredential()
    project = AIProjectClient(
        endpoint=config["project_endpoint"], credential=credential
    )
    return credential, project


def deploy(*, replace: bool = False) -> None:
    from azure.ai.projects.models import (
        AutoCodeInterpreterToolParam,
        CodeInterpreterTool,
        PromptAgentDefinition,
    )
    from dotenv import load_dotenv

    load_dotenv()
    config = required_config(os.environ)
    previous = load_state(STATE_PATH)
    if previous is not None and not replace:
        raise RuntimeError(
            f"Deployment state already exists at {STATE_PATH}. Use 'replace' or 'cleanup'."
        )

    instructions = compose_instructions(KNOWLEDGE_DIR, INSTRUCTIONS_PATH)
    upload_paths, warnings = collect_upload_paths(
        GOLD_CSV_DIR, HELPER_PATH, CATALOG_PATH, PREDICTION_DIR
    )

    credential, project = _clients(config)
    with credential, project, project.get_openai_client() as openai:
        def create_agent(file_ids: list[str]):
            return project.agents.create_version(
                agent_name=config["agent_name"],
                definition=PromptAgentDefinition(
                    **prompt_agent_options(
                        config["model_deployment"],
                        instructions,
                        [
                        CodeInterpreterTool(
                            container=AutoCodeInterpreterToolParam(file_ids=file_ids)
                        )
                        ],
                    )
                ),
                description="Manufacturing control-tower demo agent",
            )

        agent, file_ids = provision_resources(openai, upload_paths, create_agent)
        state = {
            "agent_name": agent.name,
            "agent_version": str(agent.version),
            "file_ids": file_ids,
            "snapshot_id": "epic_soca_6rn73kkx4n",
            "created_at": datetime.now(UTC).isoformat(),
        }
        finalize_deployment(
            project,
            openai,
            state,
            previous=previous,
            state_path=STATE_PATH,
        )

    print(f"Agent deployed: {state['agent_name']} version {state['agent_version']}")
    print(f"Uploaded files: {len(state['file_ids'])}")
    for warning in warnings:
        print(f"WARNING: {warning}")
    print("Open Build > Agents in Microsoft Foundry and select this agent to chat.")


def cleanup() -> None:
    from dotenv import load_dotenv

    load_dotenv()
    config = required_config(os.environ)
    state = load_state(STATE_PATH)
    if state is None:
        print("No recorded manufacturing-agent deployment to clean up.")
        return

    credential, project = _clients(config)
    with credential, project, project.get_openai_client() as openai:
        cleanup_recorded_resources(project, openai, state)
    STATE_PATH.unlink()
    print(
        f"Deleted agent {state['agent_name']} version {state['agent_version']} "
        f"and {len(state['file_ids'])} uploaded files."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("deploy", "replace", "cleanup"))
    args = parser.parse_args()
    try:
        if args.command == "cleanup":
            cleanup()
        else:
            deploy(replace=args.command == "replace")
    except Exception as error:
        print(f"FAIL: {type(error).__name__}: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
