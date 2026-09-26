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
RISK_TABLE_DIR = ROOT / "data/bi_tables"
HELPER_PATH = ROOT / "src/analysis_helper.py"
CATALOG_PATH = ROOT / "knowledge/dataset_catalog.json"
KNOWLEDGE_DIR = ROOT / "knowledge"
INSTRUCTIONS_PATH = ROOT / "src/agent_instructions.md"
CHECKLIST_PATH = ROOT / "src/answer_checklist.md"
STATE_PATH = ROOT / ".foundry/manufacturing-agent-state.json"
APPROVED_MODEL = "gpt-5-mini"
# gpt-6-luna is on trial against the approved model; see README "Model trial".
ALLOWED_MODELS = (APPROVED_MODEL, "gpt-6-luna")
REASONING_EFFORTS = ("low", "medium", "high", "xhigh", "max")
DEFAULT_REASONING_EFFORT = "medium"
SNAPSHOT_ID = "epic_soca_6rn73kkx4n"
# Small assets that change with the prompt; the large data files are reused.
REFRESHED_ON_UPDATE = frozenset({"analysis_helper.py", "dataset_catalog.json"})


def required_config(environ: Mapping[str, str]) -> dict[str, str]:
    names = (
        "FOUNDRY_PROJECT_ENDPOINT",
        "FOUNDRY_MODEL_DEPLOYMENT",
        "FOUNDRY_AGENT_NAME",
    )
    missing = [name for name in names if not environ.get(name, "").strip()]
    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
    model = environ["FOUNDRY_MODEL_DEPLOYMENT"]
    if model not in ALLOWED_MODELS:
        raise ValueError(
            f"FOUNDRY_MODEL_DEPLOYMENT must be one of {ALLOWED_MODELS} for this demo"
        )
    effort = environ.get("FOUNDRY_REASONING_EFFORT", "").strip() or DEFAULT_REASONING_EFFORT
    if effort not in REASONING_EFFORTS:
        raise ValueError(f"FOUNDRY_REASONING_EFFORT must be one of {REASONING_EFFORTS}")
    if effort == "max" and not model.startswith("gpt-6"):
        raise ValueError("Reasoning effort 'max' is only supported on GPT-6 models")
    return {
        "project_endpoint": environ["FOUNDRY_PROJECT_ENDPOINT"],
        "model_deployment": model,
        "agent_name": environ["FOUNDRY_AGENT_NAME"],
        "reasoning_effort": effort,
    }


def state_path(environ: Mapping[str, str]) -> Path:
    """The deployment state file; a trial agent sets FOUNDRY_STATE_FILE to keep its own."""
    override = environ.get("FOUNDRY_STATE_FILE", "").strip()
    return ROOT / override if override else STATE_PATH


def prompt_agent_options(
    model: str,
    instructions: str,
    tools: Sequence[Any],
    reasoning_effort: str = DEFAULT_REASONING_EFFORT,
) -> dict[str, Any]:
    return {
        "model": model,
        "instructions": instructions,
        "tools": list(tools),
        "reasoning": {"effort": reasoning_effort},
        # Concise answers for a manager audience; format is left at the default (text).
        "text": {"verbosity": "low"},
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


def provision_update(
    openai: Any,
    upload_paths: Sequence[Path],
    reuse: Mapping[str, str],
    create_agent: Callable[[list[str]], Any],
) -> tuple[Any, list[str], list[str]]:
    """Reuse recorded file IDs by filename and upload only the files not in `reuse`."""
    file_ids: list[str] = []
    uploaded: list[str] = []
    try:
        for path in upload_paths:
            if path.name in reuse:
                file_ids.append(reuse[path.name])
                continue
            with path.open("rb") as handle:
                file_id = openai.files.create(purpose="assistants", file=handle).id
            file_ids.append(file_id)
            uploaded.append(file_id)
        return create_agent(file_ids), file_ids, uploaded
    except Exception:
        for file_id in uploaded:
            try:
                openai.files.delete(file_id)
            except Exception:
                pass
        raise


def reusable_files(
    state: Mapping[str, Any], filename_of: Callable[[str], str]
) -> dict[str, str]:
    """Map recorded filenames to file IDs, leaving out the assets refreshed on every update."""
    if "files" in state:
        files = dict(state["files"])
    else:
        # States written before filenames were recorded hold only IDs.
        files = {filename_of(file_id): file_id for file_id in state["file_ids"]}
    return {name: file_id for name, file_id in files.items() if name not in REFRESHED_ON_UPDATE}


def updated_state(
    previous: Mapping[str, Any],
    *,
    agent_version: str,
    files: Mapping[str, str],
    model_deployment: str,
    reasoning_effort: str = DEFAULT_REASONING_EFFORT,
) -> dict[str, Any]:
    """Record the new version while retaining the previous one for rollback and cleanup."""
    file_ids = list(files.values())
    replaced = [file_id for file_id in previous["file_ids"] if file_id not in file_ids]
    retained = list(previous.get("retained", []))
    retained.append({"agent_version": previous["agent_version"], "file_ids": replaced})
    return {
        "agent_name": previous["agent_name"],
        "agent_version": agent_version,
        "file_ids": file_ids,
        "files": dict(files),
        "retained": retained,
        "snapshot_id": previous.get("snapshot_id", SNAPSHOT_ID),
        "model_deployment": model_deployment,
        "reasoning_effort": reasoning_effort,
        "created_at": datetime.now(UTC).isoformat(),
    }


def cleanup_recorded_resources(
    project: Any, openai: Any, state: Mapping[str, Any]
) -> None:
    failures: list[str] = []
    versions = [(state["agent_version"], state["file_ids"])] + [
        (entry["agent_version"], entry["file_ids"]) for entry in state.get("retained", [])
    ]
    for version, _file_ids in versions:
        try:
            project.agents.delete_version(
                agent_name=state["agent_name"],
                agent_version=version,
            )
        except Exception as error:
            if getattr(error, "status_code", None) != 404:
                failures.append(str(error))
    for _version, file_ids in versions:
        for file_id in file_ids:
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


def _agent_creator(project: Any, config: Mapping[str, str], instructions: str):
    from azure.ai.projects.models import (
        AutoCodeInterpreterToolParam,
        CodeInterpreterTool,
        PromptAgentDefinition,
    )

    def create_agent(file_ids: list[str]):
        return project.agents.create_version(
            agent_name=config["agent_name"],
            definition=PromptAgentDefinition(
                **prompt_agent_options(
                    config["model_deployment"],
                    instructions,
                    [CodeInterpreterTool(container=AutoCodeInterpreterToolParam(file_ids=file_ids))],
                    config["reasoning_effort"],
                )
            ),
            description="Manufacturing control-tower demo agent",
        )

    return create_agent


def update() -> None:
    """Create a new agent version from the current prompt, reusing uploaded data files."""
    from dotenv import load_dotenv

    load_dotenv()
    config = required_config(os.environ)
    path = state_path(os.environ)
    previous = load_state(path)
    if previous is None:
        raise RuntimeError("No recorded deployment to update. Use 'deploy' first.")

    instructions = compose_instructions(KNOWLEDGE_DIR, INSTRUCTIONS_PATH, CHECKLIST_PATH)
    upload_paths, _warnings = collect_upload_paths(
        GOLD_CSV_DIR, HELPER_PATH, CATALOG_PATH, RISK_TABLE_DIR
    )

    credential, project = _clients(config)
    with credential, project, project.get_openai_client() as openai:
        reuse = reusable_files(previous, lambda file_id: openai.files.retrieve(file_id).filename)
        missing = {path.name for path in upload_paths} - set(reuse) - REFRESHED_ON_UPDATE
        if missing:
            raise RuntimeError(f"Recorded deployment lacks files: {sorted(missing)}; use 'replace'")
        agent, file_ids, uploaded = provision_update(
            openai, upload_paths, reuse, _agent_creator(project, config, instructions)
        )
        state = updated_state(
            previous,
            agent_version=str(agent.version),
            files={path.name: file_id for path, file_id in zip(upload_paths, file_ids)},
            model_deployment=config["model_deployment"],
            reasoning_effort=config["reasoning_effort"],
        )
        try:
            save_state(path, state)
        except Exception:
            cleanup_recorded_resources(
                project,
                openai,
                {"agent_name": agent.name, "agent_version": str(agent.version), "file_ids": uploaded},
            )
            raise

    print(f"Agent updated: {state['agent_name']} version {state['agent_version']}")
    print(f"Reused files: {len(file_ids) - len(uploaded)}; uploaded: {len(uploaded)}")
    print(f"Previous version {previous['agent_version']} retained for rollback.")


def deploy(*, replace: bool = False) -> None:
    from dotenv import load_dotenv

    load_dotenv()
    config = required_config(os.environ)
    path = state_path(os.environ)
    previous = load_state(path)
    if previous is not None and not replace:
        raise RuntimeError(
            f"Deployment state already exists at {path}. Use 'update', 'replace' or 'cleanup'."
        )

    instructions = compose_instructions(KNOWLEDGE_DIR, INSTRUCTIONS_PATH, CHECKLIST_PATH)
    upload_paths, warnings = collect_upload_paths(
        GOLD_CSV_DIR, HELPER_PATH, CATALOG_PATH, RISK_TABLE_DIR
    )

    credential, project = _clients(config)
    with credential, project, project.get_openai_client() as openai:
        agent, file_ids = provision_resources(
            openai, upload_paths, _agent_creator(project, config, instructions)
        )
        state = {
            "agent_name": agent.name,
            "agent_version": str(agent.version),
            "file_ids": file_ids,
            "files": {path.name: file_id for path, file_id in zip(upload_paths, file_ids)},
            "snapshot_id": SNAPSHOT_ID,
            "model_deployment": config["model_deployment"],
            "reasoning_effort": config["reasoning_effort"],
            "created_at": datetime.now(UTC).isoformat(),
        }
        finalize_deployment(
            project,
            openai,
            state,
            previous=previous,
            state_path=path,
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
    path = state_path(os.environ)
    state = load_state(path)
    if state is None:
        print("No recorded manufacturing-agent deployment to clean up.")
        return

    credential, project = _clients(config)
    with credential, project, project.get_openai_client() as openai:
        cleanup_recorded_resources(project, openai, state)
    path.unlink()
    print(
        f"Deleted agent {state['agent_name']} version {state['agent_version']} "
        f"and {len(state['file_ids'])} uploaded files."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("deploy", "update", "replace", "cleanup"))
    args = parser.parse_args()
    try:
        if args.command == "cleanup":
            cleanup()
        elif args.command == "update":
            update()
        else:
            deploy(replace=args.command == "replace")
    except Exception as error:
        print(f"FAIL: {type(error).__name__}: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
