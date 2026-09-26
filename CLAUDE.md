# CLAUDE.md

@AGENTS.md

`AGENTS.md` (imported above) holds the durable business rules and target architecture. This file records how the repository **actually works today** and the V1 decisions that override parts of `AGENTS.md`.

## V1 reality vs. AGENTS.md target

`AGENTS.md` describes the end-state: Foundry calls a **Fabric Data Agent**. That is deliberately deferred because Fabric Data Agent needs paid F2+ capacity, which is not available. The accepted V1 decision (`docs/Foundry_Agent_Dataset_Decision.md`, `docs/Manufacturing_Control_Tower_Foundry_Agent_PRD.md`, `docs/superpowers/specs/2026-09-23-foundry-manufacturing-agent-design.md`) is:

- One **Foundry prompt agent** with one built-in **Code Interpreter** tool, and no function tools, MCP, File Search or hosted agent.
- The agent analyzes uploaded CSV snapshots in the Python sandbox (`/mnt/data/assistant-<fileid>-<name>`). Parquet is not a supported Code Interpreter upload type, so only CSV is uploaded.
- The Foundry Playground is the chat surface. SDK conversations are used only by the evaluators.
- The data is synthetic and static, with `data_as_of = 2026-09-15`. September 2026 is a partial month.

Keep the V1 path working and keep the Fabric Data Agent path possible later. Do not add a direct query path that would compete with the future Fabric Data Agent integration.

## Layout

| Path | Role |
|---|---|
| `src/agent_instructions.md` | Core operating rules for the agent, placed first in the composed prompt: role, grounding, the "only report what you printed" rule, the sandbox setup snippet (`EXPECTED_FILES = 19`, `DATA_NOT_LOADED` check) and the answer style |
| `knowledge/business_context.md`, `table_context.md`, `analysis_examples.md` | Composed after the core rules by `src/agent_assets.compose_instructions`. They hold the business glossary and time windows, the schema of the 17 loaded tables (limited to 18,000 chars), and 10 analysis playbooks |
| `src/answer_checklist.md` | The "Before you send" self-check, composed **last** on purpose so it is the most recent thing the model reads |
| `knowledge/dataset_catalog.json` | Machine-readable schema for 16 Gold tables (13 uploaded) plus 4 risk tables. It is **uploaded** to the sandbox, not put in the prompt, and read through `ah.catalog_tables` |
| `src/analysis_helper.py` | Uploaded to the sandbox. Provides `find_uploaded_file`, `show_table`/`format_table` (at most 8 columns and 15 rows, business formats), `SITE_NAMES`, `SIGNAL_LABELS`, `main_signal_by_line`, `catalog_tables` and `NOT_UPLOADED`. It must stay generic, with no question-specific logic |
| `src/agent_assets.py` | Validates and collects the upload set: 13 Gold CSVs, 4 risk CSVs, the helper and the catalog, **19 files** (enforced) |
| `scripts/create_agent.py` | **Canonical deploy.** `deploy` / `update` / `replace` / `cleanup`. `update` reuses uploaded data files and retains the previous version. The model is `gpt-5-mini` (or `gpt-6-luna` for a trial). `FOUNDRY_REASONING_EFFORT` and `FOUNDRY_STATE_FILE` are optional overrides. It writes `.foundry/manufacturing-agent-state.json` |
| `scripts/evaluate_demo.py` + `evaluations/demo_questions.json` | **Primary eval.** 19 natural-language cases: 10 golden (demo chats `demo_1` and `demo_2`, tagged quick or deep), 3 alternates, 2 variants and 4 metadata, run as one conversation per group, one group at a time. `--cases evaluations/demo_candidates.json` runs the 15 candidates the golden set was chosen from. It checks oracle values, record IDs against `fact_sales`, word limits, style and sandbox load, and writes answers, traces and `report.md` to `.foundry/demo-evaluation/<run-id>/` |
| `scripts/compute_demo_oracles.py` | Stdlib recomputation of the demo oracle values from the CSVs, using the glossary definitions |
| `scripts/trace_query.py` | Asks one question (optionally continuing a conversation) and prints code, sandbox output and the answer. Saves the trace to `.foundry/traces/` |
| `scripts/evaluate_agent.py` + `evaluations/golden_questions.json` | Older numeric eval, which needs an `evaluation_json` trailer. Secondary |
| `src/evaluation.py` | Pure scoring, style phrases, word counting and retry logic (429, 409 `container_expired`, connection errors) shared by both evaluators |
| `data/gold_snapshots/epic_soca_6rn73kkx4n/.../csv/` | 16 Gold CSVs (~400 MB, untracked). **Do not modify** |
| `data/bi_tables/` | Late-order-risk package (`logistic_regression:v1`, trained to 2026-08-31, **replay** generated 2026-09-23): `late_order_risk`, `late_order_risk_factors`, `order_operational_evidence`, `late_order_model_metrics` |
| `data/raw/manufacturing_order_inventory_dataset/` | Original raw synthetic dataset plus `data_dictionary.csv` |

Legacy and exploratory files that are **not** part of the manufacturing agent: `src/instructions.py`, `src/tools/business_data.py` (hard-coded regional sales stub), `scripts/chat_agent.py`, `scripts/check_*.py`, `scripts/deploy_model.py`, `main.py`. Untracked experiments: `scripts/select_foundry_files.py` and `scripts/configure_manufacturing_agent.py` (a separate `manufacturing-insight-poc` agent that reuses already-uploaded file IDs from `foundry_file_manifest.json`). `apm_modules/`, `.agents/` and `.codex/` are vendored skills and tool config.

## Commands (Windows, PowerShell)

`uv run` can hang here because company antivirus blocks extraction into the uv cache. Call the venv interpreter directly:

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests          # offline, ~0.2s, no Azure
.venv\Scripts\python.exe -m unittest tests.test_evaluation -v    # one module
.venv\Scripts\python.exe scripts\create_agent.py update          # new agent version from the current prompt; reuses data files
.venv\Scripts\python.exe scripts\evaluate_demo.py --all          # connected; costs tokens + Code Interpreter sessions
.venv\Scripts\python.exe scripts\evaluate_demo.py --group B
.venv\Scripts\python.exe scripts\trace_query.py "question"
```

Connected commands need `az login` and `.env` (`FOUNDRY_PROJECT_ENDPOINT`, `FOUNDRY_MODEL_DEPLOYMENT`, `FOUNDRY_AGENT_NAME`). The agent deploys with `reasoning.effort = "medium"` and `text.verbosity = "low"`. Deploying and running evaluations spend money. Claude Code's auto mode blocks `create_agent.py` as a production deploy, so the user runs deploys, and evaluations too when asked.

## Conventions

- Tests use stdlib `unittest` with hand-written fakes at the SDK boundary (see `tests/test_agent_deployment.py`). Production modules import Azure SDKs **lazily inside functions** so tests run without them. Keep it that way.
- Write the failing test first for new behavior. Commits are small and phase-scoped, with messages like `feat: …`, `fix: …`, `docs: …`.
- Knowledge files may describe data, joins and rules, but must not embed snapshot-specific answer values the model could memorize. Evaluation oracles belong in `evaluations/*.json` only.
- Never hard-code endpoints, resource names or file IDs in source. `.env` and `.foundry/*` state stay local.

## Known issues (as of 2026-09-25)

- **The demo set is frozen at agent v27** (golden chats `demo_1` and `demo_2` passed 8/10: `.foundry/demo-evaluation/20260925T132451Z` and `20260925T133833Z`). Do not change the prompt before the demo without a full re-run of both chats.
- The remaining failures are population drift, not wrong conclusions:
  - the Pune recovery plan sometimes sizes itself by backorder need instead of revenue at risk;
  - the quality-holds question sometimes uses the whole June–September horizon.
- Occasional single code words (for example `blocked_qty`) slip into prose.
- One `400 invalid_prompt` usage-policy false positive was seen on the recovery-plan question.
- Sandbox file mounting is sometimes slow or partial. The setup waits up to 60 s and raises `DATA_NOT_LOADED`; the agent retries once, then asks the user to start a new chat. The evaluator flags both the raised error and the fallback reply.
- Latency is usually 15–80 s per answer, with rare service-side outliers (one answer took 667 s with a single code call).
- gpt-5-mini has run-to-run variation in wording and length. Judge prompt changes on a full eval run, not on one answer.
- `.env` is tracked in git even though `.gitignore` lists it. It contains resource names and endpoints, not keys.
