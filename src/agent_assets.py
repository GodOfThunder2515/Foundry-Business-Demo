"""Validate and assemble the local assets used by the prompt agent."""

from __future__ import annotations

import json
from pathlib import Path


from src.analysis_helper import NOT_UPLOADED


TABLE_CONTEXT_LIMIT = 18_000
RISK_TABLE_FILENAMES = (
    "late_order_risk.csv",
    "late_order_risk_factors.csv",
    "late_order_model_metrics.csv",
    "order_operational_evidence.csv",
)
# Attaching more files than this makes Code Interpreter mount only some of them.
CODE_INTERPRETER_FILE_LIMIT = 20
# 13 Gold tables + helper + catalog + 4 risk tables; the prompt's setup check must match.
EXPECTED_UPLOAD_COUNT = 19


def _read_required(path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(f"Required agent asset not found: {path.name}")
    return path.read_text(encoding="utf-8").strip()


def compose_instructions(
    knowledge_dir: Path, instructions_path: Path, checklist_path: Path | None = None
) -> str:
    sections = [
        ("Core operating instructions", _read_required(instructions_path)),
        ("Business context", _read_required(knowledge_dir / "business_context.md")),
        ("Table context", _read_required(knowledge_dir / "table_context.md")),
        ("Analysis playbooks", _read_required(knowledge_dir / "analysis_examples.md")),
    ]
    if checklist_path is not None:
        # Last, so the pre-send self-check is the most recent thing the model read.
        sections.append(("Before you send", _read_required(checklist_path)))
    table_context = sections[2][1]
    if len(table_context) > TABLE_CONTEXT_LIMIT:
        raise ValueError(
            f"table_context.md exceeds the 18,000 character limit: {len(table_context)}"
        )
    return "\n\n".join(f"# {title}\n\n{content}" for title, content in sections)


def collect_upload_paths(
    gold_csv_dir: Path,
    helper_path: Path,
    catalog_path: Path,
    risk_table_dir: Path | None = None,
) -> tuple[list[Path], list[str]]:
    if not helper_path.is_file():
        raise FileNotFoundError(f"Required agent asset not found: {helper_path.name}")
    if not catalog_path.is_file():
        raise FileNotFoundError(f"Required agent asset not found: {catalog_path.name}")

    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    paths: list[Path] = []
    for name in sorted(set(catalog["tables"]) - NOT_UPLOADED):
        path = gold_csv_dir / catalog["tables"][name]["filename"]
        if not path.is_file():
            raise FileNotFoundError(f"Required Gold file not found: {path.name}")
        paths.append(path)
    paths.extend((helper_path, catalog_path))

    for filename in RISK_TABLE_FILENAMES:
        path = risk_table_dir / filename if risk_table_dir is not None else None
        if path is None or not path.is_file():
            raise FileNotFoundError(f"Required risk table not found: {filename}")
        paths.append(path)
    if len(paths) != EXPECTED_UPLOAD_COUNT:
        raise ValueError(
            f"Upload set has {len(paths)} files but the prompt expects {EXPECTED_UPLOAD_COUNT}"
        )
    return paths, []
