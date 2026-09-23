# Foundry Manufacturing Operations Agent Design

## Status

Proposed design approved in conversation on 2026-09-23. This specification requires user review before implementation planning begins.

## Purpose

Build a simple Microsoft Foundry prompt agent that analyzes the existing manufacturing Gold snapshot with Code Interpreter and explains operational risk in business language.

The agent must answer the central control-tower question:

> Which customer commitments are at risk, why are they at risk, what recovery action is worth taking, who must approve it, and what evidence supports the recommendation?

The first version is a demonstration system. It is specialized for the supplied synthetic manufacturing dataset but must handle reasonable open-ended questions within that dataset. Approximately 15 to 20 golden questions provide evaluation coverage; they are not a fixed question menu.

## Constraints

- Complete the first usable version quickly, without a new platform layer.
- Use the existing Microsoft Foundry project and `gpt-4.1-mini` deployment.
- Use a Foundry prompt agent, not a hosted agent.
- Use the built-in Code Interpreter as the only V1 tool.
- Do not require `azd`, Fabric Data Agent, File Search, an MCP server, a vector store, or a custom code-interpreter service.
- Do not add, reshape, or denormalize Gold tables.
- Do not implement natural-language-to-SQL.
- Do not use the existing hard-coded regional-sales function tool.
- Do not execute controlled business changes; recommendations require human approval.

## Data decision

The agent receives the 16 CSV exports already present in:

`data/gold_snapshots/epic_soca_6rn73kkx4n/named-outputs/snapshot/csv/`

The upstream Gold layer remains unchanged. The data is synthetic and has an explicit as-of date of `2026-09-15`.

The default analytical horizon is June through September 2026:

- Historical events: `2026-06-01` through `2026-09-15`.
- Commitments: promised dates from `2026-06-01` through `2026-09-30`.
- Current operational views: overdue active commitments and commitments due in the next 7, 14, or 30 days, depending on the question.
- Current-state tables, such as inventory lots, use the available current snapshot.
- Open or unresolved records remain eligible when they affect the selected population, even if created before June.

The existing files remain complete working data for Python. Data rows are not copied into the prompt.

Four Azure Machine Learning outputs will be accepted through stable local interface filenames when available:

- `late_order_risk_predictions.csv`
- `supplier_receipt_risk_predictions.csv`
- `production_completion_risk_predictions.csv`
- `quality_risk_predictions.csv`

The upload process may map upstream filenames to these interface names without changing their source tables. Each prediction file must include the scored entity key, prediction timestamp, model name, model version, probability, risk band, reason codes, and actual outcome when available.

## High-level architecture

```text
User in Foundry Playground
    |
    v
Foundry Prompt Agent
    |-- Core operating instructions
    |-- Manufacturing business context
    |-- Compact all-table context
    |-- Three to five analysis examples
    |
    v
Built-in Code Interpreter
    |-- Existing Gold CSV files
    |-- Four prediction files when available
    |-- dataset_catalog.json
    `-- analysis_helper.py
    |
    v
Python analyzes the complete matching population
    |
    v
analysis_helper.py sorts, limits, and formats the result
    |
    v
Agent explains findings, evidence, recovery options, and uncertainty
```

There is one agent and one tool. Foundry performs the normal model-to-Code-Interpreter orchestration. The application does not implement a separate planner, table-selection model, multi-agent coordinator, or domain function catalogue.

## Repository knowledge artifacts

Knowledge is maintained as separate reviewable files rather than one monolithic source file.

```text
knowledge/
  business_context.md
  table_context.md
  analysis_examples.md
  dataset_catalog.json

src/
  agent_instructions.md
  analysis_helper.py
```

The deployment script composes the four Markdown sources into the prompt agent's instruction payload. This gives mandatory rules to the model reliably without adding File Search. `dataset_catalog.json` and `analysis_helper.py` are uploaded with the business data and mounted in Code Interpreter.

### Core agent instructions

`agent_instructions.md` contains only operational rules:

- agent role and business objective;
- mandatory Code Interpreter use for company-specific quantitative claims;
- grounding and uncertainty requirements;
- distinction among facts, predictions, analytical inferences, and proposals;
- analysis-result limits;
- response requirements;
- human-approval boundaries;
- prohibited behavior, including invented data and unsupported causation.

### Business context

`business_context.md` is a concise operating manual derived from the manufacturing workflow requirement. It defines:

- the order-to-cash and inventory-control workflow;
- customer commitments and sales-order-line grain;
- commercial, supply, production, inventory, quality, fulfillment, and finance concepts;
- risk versus cause versus actionability;
- backlog, available-to-promise, OTIF, revenue-at-risk, and related metric rules supported by the data;
- cause categories and recovery logic;
- approval responsibilities;
- snapshot, partial-period, and evidence limitations.

It must not reproduce the entire requirements document or include unstable business values.

### Compact table context

`table_context.md` gives the model initial awareness of all 16 Gold tables and the four prediction interfaces. It does not contain complete schemas or data samples.

Each entry contains only:

- table name;
- grain;
- primary key;
- main join keys;
- one-sentence purpose;
- one warning when required.

Example:

```text
fact_shipments — Shipment-line grain. Key: shipment_line_id.
Joins to sales by sales_order_line_id. Contains planned and actual dates,
carrier, freight, short shipment, and logistics exceptions.
```

The complete compact table context is included once as part of the agent instructions. There is no primary-versus-other table selector, keyword router, question classifier, or per-request schema-context builder.

The table context must remain below 12,000 characters. It contains no sample rows, sampled values, statistics, or complete column lists.

### Analysis examples

`analysis_examples.md` contains three to five methodological examples rather than fixed answers. The examples cover:

1. Risk ranking.
2. Period comparison.
3. Root-cause investigation.
4. Recovery-option comparison.
5. An unsupported or uncertain question.

Each example records the question, population, relevant tables, grain, calculation sequence, evidence hierarchy, caveats, and expected response organization. Examples contain no snapshot-specific answer values that the model could memorize.

### Dataset catalog

`dataset_catalog.json` contains exact machine-readable technical metadata:

- filenames;
- complete column names and expected types;
- table grain and primary keys;
- supported joins and cardinality;
- date fields and formats;
- controlled values where stable;
- aggregation warnings;
- evidence classification;
- known limitations.

The JSON catalog is not inserted wholesale into model context. Code Interpreter reads only the entries needed for the current analysis.

## Schema exploration

The agent starts with the compact table context. For a quantitative question it:

1. Identifies the likely tables from their short descriptions.
2. Uses Code Interpreter to read the relevant catalog entries or CSV headers.
3. Validates required fields against the actual files.
4. Loads only the columns required for the analysis where practical.
5. Applies the documented filters and date rules.
6. Aggregates child facts to the target grain before joining.
7. Runs the analysis over every matching row.

The helper exposes a bounded schema-inspection function for no more than five tables per call. The agent may make another inspection call when the question genuinely spans more tables.

The agent must not silently replace a missing field, infer an undocumented relationship, or use `dim_region` for attribution while its relationship remains undocumented.

## Analysis helper

`analysis_helper.py` provides generic safeguards and file handling. It does not contain question-specific analytics.

Required responsibilities:

- locate mounted files despite Foundry file-ID prefixes;
- map logical table names to physical CSV files;
- read selected catalog entries;
- read headers and validate required columns;
- parse documented `yyyyMMdd` date keys consistently;
- apply deterministic result sorting;
- limit grouped results to 15 rows;
- limit detailed order-line results to 10 rows by default;
- limit returned tables to 12 columns;
- preserve total matched counts when details are truncated;
- mark truncation explicitly;
- build the single final analysis-result object.

The helper must not implement functions such as `answer_pune_risk_question` or encode the golden answers.

The output limit is a demo guardrail, not a security boundary. Prompt rules instruct the agent not to print or display intermediate dataframes. The helper applies the cap to intended outputs, and evaluation rejects uncapped behavior. A custom tool boundary would be required for a non-bypassable data-access control and is outside V1.

## Join and evidence rules

The agent follows these non-negotiable rules:

1. Start customer-commitment analysis at `sales_order_line_id` grain.
2. Join dimensions through their surrogate keys.
3. Join shipments to sales through `sales_order_line_id`.
4. Aggregate one-to-many child facts before joining them to sales lines.
5. Never multiply order value, quantity, inventory, invoice value, or prediction counts through a many-to-many join.
6. Parse fact date keys directly when `dim_date` does not cover them. `dim_date` ends on `2026-09-15`, while facts contain later commitments.
7. Do not present procurement, production, reservation, or quality signals as confirmed causes for a customer line unless a documented relationship supports that attribution.
8. Label product-, warehouse-, site-, or time-associated evidence as an associated operational signal.
9. Distinguish recorded facts, model probabilities, model reason codes, analytical inferences, and proposed actions.
10. Exclude blocked, expired, quality-held, or reserved inventory from freely available inventory when the required fields support that calculation.

## Request lifecycle

### Deployment

A setup script:

1. Validates the required Gold files.
2. Uploads each file once with purpose `assistants`.
3. Uploads `dataset_catalog.json` and `analysis_helper.py`.
4. Includes available prediction files and records missing optional prediction inputs.
5. Reads and composes the Markdown instruction sources.
6. Creates a version of the existing Foundry prompt agent using `gpt-4.1-mini`.
7. Attaches one `CodeInterpreterTool` with the uploaded file IDs.
8. Records created agent and file identifiers for later cleanup or replacement.

The V1 upload contract is CSV because the repository's connected Code Interpreter smoke test has already validated CSV. The equivalent local Parquet files remain useful for local profiling but are not attached until a separate Foundry upload-and-read test establishes support.

### Conversation

Foundry Playground is the V1 chat surface and uses the persisted prompt-agent version. A conversation normally reuses one Code Interpreter session, reducing repeated loading work. Session state is only a performance optimization; every answer still records scope, filters, and data-as-of information. SDK conversations are used only by automated validation and evaluation.

For each question:

1. Determine whether the request asks for company-specific data.
2. For definitions and policy questions, answer from business context without Python.
3. For quantities, rankings, trends, causes, orders, or recommendations, call Code Interpreter.
4. Select and validate the relevant tables.
5. Compute over the complete matching population.
6. Pass the intended final result through `analysis_helper.py`.
7. Explain the result in business language.

The built-in Code Interpreter call is orchestrated by Foundry; V1 does not maintain an interactive CLI or the custom function-call loop used by the repository's existing sales stub.

## Analysis-result contract

The intended final Python output follows this shape:

```json
{
  "population": {
    "matched_rows": 0,
    "filters": [],
    "data_as_of": "2026-09-15"
  },
  "summary_metrics": {},
  "top_results": [],
  "warnings": [],
  "truncated": false
}
```

Limits:

- maximum 15 rows in a grouped result;
- maximum 10 detailed order lines unless the user asks for a subsequent page;
- maximum 12 columns in a returned table;
- always return the complete matched-row count;
- sort by a documented business rule before truncation;
- never print a complete dataframe, CSV, or unbounded list;
- keep full intermediate dataframes in Python;
- support explicit pagination for requests such as “show the next 10.”

The default risk ranking is risk probability or band, then business priority, promised-date urgency, line value, and backordered quantity. The user's requested ranking overrides the default.

## User-facing response design

The agent adds explanation and decision support beyond a table-retrieval layer. Responses adapt to the question and may be moderately detailed for multi-step analysis.

### Business conclusion

Lead with the decision-relevant finding rather than a method description.

### Population and scope

State the as-of date, time window, filters, number of lines or orders, and prediction model version when applicable.

### Analysis performed

Provide a concise, auditable account of the analytical sequence and the material result at each stage. Explain method and evidence, not hidden chain-of-thought or raw Python code.

### Findings and explanation

Explain what changed, where it is concentrated, the contribution of each major driver, whether evidence is direct or inferred, and why it matters operationally.

### Recovery options

When appropriate, compare affected commitments, expected benefit, estimated cost, assumptions, and required approval. If cost is unavailable, state that a lowest-cost ranking is incomplete.

### Order-level evidence

Show at most 10 representative or highest-priority lines and state the selection rule and complete matching population.

### Limitations

State missing relationships, unavailable costs, partial periods, model-versus-operational evidence, associated signals that are not proven causes, and truncation.

Typical depth:

- simple lookup: a few paragraphs;
- comparison or diagnostic question: approximately 400 to 700 words;
- multi-step cause or recovery analysis: approximately 700 to 1,200 words;
- detailed methodology only when requested.

Tables support the narrative; they do not replace it.

## Error handling

| Condition | Required behavior |
|---|---|
| Missing file | Name the missing input and answer only the supported portion. |
| Missing column | Do not substitute another field silently. |
| No matching rows | Report zero matches and repeat the material filters. |
| Unsupported join | Describe only an associated signal, not a confirmed cause. |
| First Python error | Correct the code and retry once with a simpler analysis. |
| Second Python error | Explain what could not be calculated without inventing a result. |
| Oversized result | Sort, truncate through the helper, and report the full count. |
| Missing action cost | Provide a conditional recommendation and say cost ranking is incomplete. |
| Partial September period | Label it partial and avoid a misleading full-month comparison. |
| Controlled action | Propose it and name the required human approval; do not claim execution. |

## Evaluation strategy

V1 uses one small JSON evaluation dataset and a lightweight runner rather than a new evaluation framework.

The evaluation set contains approximately 15 to 20 golden questions plus paraphrases. Each case may specify:

- expected filters and population;
- expected numerical values or tolerance;
- whether Code Interpreter is required;
- required evidence categories;
- prohibited claims;
- maximum detailed rows;
- required uncertainty or refusal behavior.

Evaluation checks:

1. Code Interpreter is invoked for company-specific quantitative claims.
2. Numerical results match a local Python oracle.
3. Material filters and `data_as_of` appear.
4. Model-visible details remain within the cap.
5. Facts, predictions, model drivers, and inferences remain distinct.
6. Unsupported causal claims are not made.
7. Controlled actions require human approval.
8. Partial periods are qualified correctly.
9. Rephrased and adjacent questions use the same business rules rather than memorized answers.

At least three golden questions require multi-step analysis and an aggregate-to-order-line drill-down.

## Observability and cost controls

- Reuse one conversation for a user's interactive session.
- Avoid parallel Code Interpreter conversations during the demo.
- Record agent version, model deployment, conversation ID, response ID, tool-call presence, input snapshot identifier, and elapsed time.
- Do not log raw business rows unnecessarily.
- Uploaded project files persist until explicitly deleted; the setup workflow must support deleting replaced files and obsolete agent versions.
- Code Interpreter sessions incur charges separately from model tokens, so the CLI must not create a new conversation for every follow-up.

## Security and governance

- Authenticate with `DefaultAzureCredential`; do not store API keys in the repository.
- Keep endpoints, agent names, deployment names, and resource identifiers configurable through environment variables.
- Do not commit `.env`, tokens, uploaded-file IDs containing sensitive metadata, or credentials.
- Treat the supplied data as synthetic demo data and report the explicit as-of date.
- The agent may recommend but may not release quality or credit holds, change production schedules or promise dates, approve premium freight, alter purchase orders, or claim an action was executed.

## V1 repository changes anticipated

Implementation should remain small and reuse the current SDK pattern. The anticipated scope is:

- knowledge and instruction files described above;
- one generic analysis helper;
- one agent creation/upload script based on the working validation script;
- a persistent prompt-agent deployment script and Foundry Playground as the chat surface;
- one lightweight golden-evaluation dataset and runner;
- small tests for context budgets, catalog validity, result caps, and local oracle calculations.

No application UI, database, API service, hosted-agent container, toolbox, File Search index, or Fabric deployment is part of V1.

## Acceptance criteria

The design is implemented successfully when:

1. One Foundry prompt agent with one Code Interpreter tool can analyze the existing Gold CSV files.
2. The 16 Gold source files remain unchanged.
3. The persistent table context stays below 12,000 characters and contains no business data samples.
4. Full Python analysis is possible while intended model-visible result tables respect the 15-row, 10-detail-row, and 12-column limits.
5. The agent answers the golden evaluation set reproducibly and handles reasonable adjacent questions.
6. Multi-step responses explain population, analysis, findings, evidence, recovery options, approvals, and uncertainty when relevant.
7. Quantitative claims use Code Interpreter and report material filters and the `2026-09-15` as-of date.
8. Missing data and unsupported relationships produce qualified answers rather than fabricated causes.
9. The current regional-sales stub is not used by the manufacturing agent.
10. No new Gold table, derived agent table, infrastructure service, or business-action integration is introduced.

## References

- `docs/Foundry_Agent_Dataset_Decision.md`
- `docs/manufacturing_order_workflow_requirement.docx`
- `docs/Manufacturing_Control_Tower_Foundry_Agent_PRD.md`
- `data/gold_snapshots/epic_soca_6rn73kkx4n/named-outputs/snapshot/gold_snapshot_manifest.json`
- Microsoft Foundry Code Interpreter documentation: <https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/code-interpreter>
- Microsoft Foundry Agent Service limits: <https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/limits-quotas-regions>
