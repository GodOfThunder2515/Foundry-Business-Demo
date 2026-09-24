# Foundry Manufacturing Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Deliver a persistent Microsoft Foundry prompt agent that analyzes the existing 16-table manufacturing Gold snapshot with Code Interpreter and is demoed through Foundry Playground.

**Architecture:** Compose focused repository knowledge into prompt-agent instructions, upload the existing Gold CSVs plus a catalog and generic result helper, and attach one built-in Code Interpreter tool. Keep all calculations in Python and cap only the model-visible result.

**Tech Stack:** Python 3.12, standard-library `unittest`, pandas, `azure-ai-projects`, `azure-identity`, Microsoft Foundry prompt agents.

**Spec:** `docs/superpowers/specs/2026-09-23-foundry-manufacturing-agent-design.md`

## Global Constraints

- Preserve all 16 Gold CSV files unchanged.
- Use the existing environment-variable names and `DefaultAzureCredential`.
- Use `gpt-4.1-mini`, one prompt agent, and one built-in Code Interpreter tool.
- Maximum output: 15 grouped rows, 10 detailed rows, and 12 columns.
- No interactive CLI, hosted agent, `azd`, Fabric Data Agent, vector store, custom UI, or new Gold table.
- Write each executable behavior test first and observe the expected failure before implementation.

## Review Focus

- Future fact dates beyond `dim_date` must remain queryable.
- One-to-many joins must not duplicate order value or quantity.
- Optional prediction files must not block deployment.
- A failed deployment must remove only files uploaded by that attempt.
- Partial September and unsupported causal links must be qualified.

---

### Task 1: Local analysis contract and dataset catalog

**Files:** Create `src/analysis_helper.py`, `knowledge/dataset_catalog.json`, `tests/test_analysis_helper.py`, and `tests/test_dataset_catalog.py`.

**Interfaces:** Produce `find_uploaded_file`, `parse_yyyymmdd`, and `build_analysis_result` exactly as defined in the approved plan.

- [ ] Write failing tests for mounted-file lookup, date parsing, caps, sorting, pagination, JSON normalization, and catalog integrity.
- [ ] Run the focused tests and confirm they fail because the implementation/catalog is absent.
- [ ] Add the minimal helper and 16-table catalog.
- [ ] Run focused tests, then the complete unittest suite.
- [ ] Commit only Task 1 files.

### Task 2: Knowledge and instruction assembly

**Files:** Create `knowledge/business_context.md`, `knowledge/table_context.md`, `knowledge/analysis_examples.md`, `src/agent_instructions.md`, `src/agent_assets.py`, and `tests/test_agent_assets.py`; update the design spec for Playground-first V1.

**Interfaces:** Produce `compose_instructions` and `collect_upload_paths` exactly as defined in the approved plan.

- [ ] Write failing tests for missing Gold inputs, optional predictions, the table-context budget, instruction order, and the 18 required uploads.
- [ ] Run the focused tests and confirm the expected failures.
- [ ] Add the minimum asset-loading implementation and focused knowledge files.
- [ ] Run focused tests, local preflight, and the complete suite.
- [ ] Commit only Task 2 files.

### Task 3: Persistent Foundry prompt-agent deployment

**Files:** Replace `scripts/create_agent.py`; create `tests/test_agent_deployment.py`; update `.gitignore` for only `.foundry/manufacturing-agent-state.json`.

**Interfaces:** Support `uv run python scripts/create_agent.py deploy`, `cleanup`, and explicit `replace`.

- [ ] Write failing tests for configuration validation, state handling, duplicate refusal, and failure cleanup using a narrow fake at the remote SDK boundary.
- [ ] Run the focused tests and confirm expected failures.
- [ ] Implement persistent upload, version creation, rollback, state writing, cleanup, and safe replacement.
- [ ] Run focused tests and the complete suite.
- [ ] Deploy once and verify one fixed quantitative request contains a Code Interpreter call and matches the local oracle.
- [ ] Commit only Task 3 files.

### Task 4: Golden evaluation

**Files:** Create `evaluations/golden_questions.json`, `scripts/evaluate_agent.py`, `src/evaluation.py`, and `tests/test_evaluation.py`.

**Interfaces:** Support `--case ID`, `--smoke`, and `--all`. After connected testing showed that one 18-turn conversation exceeded token-rate limits and carried tool context between numeric oracles, isolate numeric/pagination cases and batch qualitative cases in groups of at most five. Write concise local audit results without raw rows.

- [ ] Write failing tests for case loading, selection, numeric matching, qualifier/prohibited-claim checks, detail caps, and missing-prediction expectations.
- [ ] Run the focused tests and confirm expected failures.
- [ ] Implement the minimum runner and 18-case dataset with independently reviewed literal oracles where deterministic.
- [ ] Run focused tests, five connected smoke cases, then the full suite.
- [ ] Commit only Task 4 files.

### Task 5: Demo hardening and handoff

**Files:** Update `README.md` and add no new runtime subsystem.

- [ ] Run the complete local suite, compilation check, existing disposable Code Interpreter validation, and golden evaluation.
- [ ] Review five primary answers for grounding, result caps, partial-period wording, unsupported causation, costs, and approvals.
- [ ] Document deploy, Playground, evaluation, replacement, and cleanup commands.
- [ ] Perform a whole-change review and fix Critical/Important findings through RED-GREEN tests.
- [ ] Commit the verified handoff documentation and fixes.
