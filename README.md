# Manufacturing Control Tower Foundry Agent

This repository deploys a Microsoft Foundry prompt agent (gpt-5-mini, reasoning effort medium, low verbosity) that uses Code Interpreter to analyze a synthetic manufacturing Gold snapshot and a late-order risk package. The data as-of date is fixed at `2026-09-15`. Answers are analytical demo outputs, not live operational data.

## Setup

Authenticate with the company Azure account and configure the uncommitted `.env` file:

```powershell
az login
uv sync --frozen
```

```dotenv
FOUNDRY_PROJECT_ENDPOINT=https://<resource>.services.ai.azure.com/api/projects/<project>
FOUNDRY_MODEL_DEPLOYMENT=gpt-5-mini
FOUNDRY_AGENT_NAME=manufacturing-control-tower-agent
```

`uv run` can hang when antivirus blocks the uv cache. If it does, call `.venv\Scripts\python.exe` directly in the commands below.

The agent receives **19 files**:

- 13 Gold CSVs from `data/gold_snapshots/epic_soca_6rn73kkx4n/named-outputs/snapshot/csv/`. `dim_date`, `dim_region` and `fact_inventory_transactions` are deliberately not uploaded; see `NOT_UPLOADED` in `src/analysis_helper.py`.
- The 4 late-order-risk CSVs in `data/bi_tables/`.
- `src/analysis_helper.py`.
- `knowledge/dataset_catalog.json`.

Parquet duplicates are not uploaded, because Code Interpreter does not accept them.

## How the prompt is built

`src/agent_assets.compose_instructions` joins these files, in this order, into the agent's instructions:

1. `src/agent_instructions.md`: role, grounding, sandbox setup and answer style.
2. `knowledge/business_context.md`: business concepts, time windows, populations and approvers.
3. `knowledge/table_context.md`: the schema of every uploaded table, plus how to read the catalog.
4. `knowledge/analysis_examples.md`: analysis playbooks.
5. `src/answer_checklist.md`: the "Before you send" self-check, placed last on purpose.

## Deploy and use the Playground

```powershell
uv run python scripts/create_agent.py deploy    # first version: uploads all 19 files
uv run python scripts/create_agent.py update    # new version from the current prompt; reuses data files
uv run python scripts/create_agent.py replace   # new version with every file re-uploaded
uv run python scripts/create_agent.py cleanup   # delete recorded versions and files
```

**Which command to use:**

- `update` is the normal command after a prompt change. It uploads only the helper and the catalog, and keeps the previous version for rollback.
- `replace` rebuilds everything, for use after a data change.
- `cleanup` removes the current and retained versions and their files.

State (agent name, version, file IDs, never secrets) is written to `.foundry/manufacturing-agent-state.json`.

In Microsoft Foundry, go to **Build > Agents**, select `manufacturing-control-tower-agent`, and chat in the Playground. Recommendations remain proposals and require human approval.

### Golden demo questions

These questions were chosen from 15 candidates (`evaluations/demo_candidates.json`), each run twice, for correctness, insight, stability and latency. Ask them in two chats, in this order. Send one warm-up question in each chat before presenting, so the one-time data load (about 20 s) happens off-screen.

| Chat | # | Question | Tier |
|---|---|---|---|
| 1: risk story | 1 | How exposed are we over the next two weeks, and where is the risk concentrated? | deep |
| | 2 | Which Pune orders should my planners chase first, and why? | deep |
| | 3 | What's the cheapest way to rescue the Pune orders due in the next seven days, and who needs to sign off? | deep |
| | 4 | Is paying for express freight actually worth it for our late orders? | deep |
| | 5 | Release the credit hold and book express freight for the top five Pune orders. | quick |
| 2: customers and trust | 6 | Which of our strategic customers have orders at risk of running late this week, and who should I call first? | quick |
| | 7 | How much revenue is stuck behind credit or customer holds right now? | quick |
| | 8 | Are any of those customers also behind on paying us? | quick |
| | 9 | Are quality holds really what's stopping us from shipping? | deep |
| | 10 | Can I trust the late-order predictions, and where should my planners double-check? | quick |

On gpt-5-mini, quick answers take about 25–60 s and deep answers 45–100 s.

**Frozen at agent version 27** (2026-09-25; the last two runs passed 8/10). Presenter notes:

- **Numbers that stay the same across runs:**
  - 1,406 lines and ₹4.84M at risk over two weeks;
  - Pune has 126 of 156 lines flagged;
  - holds total ₹4.10M, and 114 of those customers have ₹763.5K overdue;
  - express freight is no more on time than standard;
  - model precision 68.5% and recall 74.3%.
- **Questions 3 and 9 can vary in scope.** The Pune plan may size itself by backorder need rather than the **₹157.8K at risk**, and the quality answer may use the whole June–September order book rather than the next 14 days. The conclusions stay the same (local stock first, express not needed; quality is a real but minor blocker). If asked, anchor on the at-risk figure from question 1.
- **If an answer errors** (a rare `invalid_prompt`), re-send it. If an answer is poor, ask it again. If a new version misbehaves, point the Playground back to version 27.

- **Alternates:** on-time shipping trend, "What's going wrong at our Pune plant?" and supplier delays.
- **Other checks:** `evaluations/demo_questions.json` also holds variant and metadata questions, which check that the agent generalizes beyond this list.

**Demo tips:**

- Warm the agent up with a question or two before presenting.
- A rare `invalid_prompt` error has been seen on the recovery-plan question. Re-sending the question resolves it.

## Validate

Offline contract tests (no Azure access needed):

```powershell
uv run python -m unittest discover -s tests
```

### Demo evaluation (connected; costs tokens and Code Interpreter sessions)

```powershell
uv run python scripts/evaluate_demo.py --all
uv run python scripts/evaluate_demo.py --question risk_overview
uv run python scripts/evaluate_demo.py --group B
```

Each conversation group runs in its own conversation, one group at a time. For every answer the evaluator checks:

- required values and qualifiers from independently computed oracles (`scripts/compute_demo_oracles.py`);
- that record IDs exist in `fact_sales`;
- word limits;
- style: no column names, codes, method narration or closing offers;
- that the sandbox loaded all files.

It saves answers, traces, `run.json` and `report.md` under the ignored `.foundry/demo-evaluation/<run-id>/`.

### Trace one question

```powershell
uv run python scripts/trace_query.py "Which Pune orders due this week are most at risk?"
uv run python scripts/trace_query.py "Show the next 10." --conversation <conversation-id>
```

This prints the code, sandbox output and final answer, and saves the raw trace to `.foundry/traces/`.

The older numeric evaluation (`scripts/evaluate_agent.py` with `evaluations/golden_questions.json`) and `scripts/validate_code_interpreter.py` still work, but the demo evaluation is the primary check.

## Trying another model

`create_agent.py` accepts `gpt-5-mini` (the default) or `gpt-6-luna`, plus these optional overrides:

- `FOUNDRY_REASONING_EFFORT`: `low`, `medium`, `high`, `xhigh` or `max`. The default is `medium`, and `max` works only on GPT-6.
- `FOUNDRY_STATE_FILE`: gives a trial agent its own state file.

Set the overrides in the shell, so `.env` and the live agent are untouched:

```powershell
$env:FOUNDRY_MODEL_DEPLOYMENT="gpt-6-luna"; $env:FOUNDRY_AGENT_NAME="manufacturing-control-tower-agent-luna"
$env:FOUNDRY_STATE_FILE=".foundry/luna-agent-state.json"; $env:FOUNDRY_REASONING_EFFORT="high"
uv run python scripts/create_agent.py deploy
```

The model deployment must exist first. As of 2026-09-25, `gpt-6-luna` has no quota in this subscription, and Microsoft does not yet document Code Interpreter support for GPT-6 models in the Agent Service.
