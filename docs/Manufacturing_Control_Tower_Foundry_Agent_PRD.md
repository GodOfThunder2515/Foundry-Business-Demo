# Product Requirements Document
## Manufacturing Control Tower - Foundry Analytical Agent

**Version:** 1.0  
**Date:** 21 September 2026  
**Status:** Build-ready for demo implementation  
**Target demo:** 29 September 2026

---

## 1. Executive Summary

This PRD defines the V1 architecture for a manufacturing decision-support agent built in Microsoft Foundry. The goal is to provide a conversational analytical experience over the same manufacturing control-tower data used by Power BI, without requiring Fabric Data Agent or an F2 Fabric capacity for the demo.

The V1 agent will be a **Foundry Prompt Agent** using **Code Interpreter**. The agent will receive curated analytical snapshot files generated from Fabric Gold data. It can write and execute Python iteratively to filter, join, aggregate, compare periods, investigate anomalies, and answer follow-up questions. This gives the agent substantially more analytical freedom than a set of hard-coded business functions, while avoiding the complexity of building an NL-to-SQL engine before the demo.

The authoritative data remains in **Microsoft Fabric / OneLake**. Fabric Delta tables remain the source of truth. Their underlying data is stored as Parquet files plus the Delta transaction log. The agent does not treat its uploaded files as a new database. Instead, a small set of agent-friendly snapshots is exported from the Gold layer and uploaded to Foundry for analysis.

For V1, the agent-facing snapshots will use **CSV**, not Parquet, because the built-in Foundry Code Interpreter supports CSV but does not currently list Parquet as a supported uploaded file type. Parquet therefore remains in OneLake as part of the Fabric Delta architecture; CSV is only the temporary analysis interface for the agent.

The Power BI dashboard-context integration is deliberately deferred. In a later phase, a Power Apps visual embedded inside the Power BI report can pass the current page/filter/selection context to the agent. The V1 can be built and tested today entirely in Foundry using the analytical snapshots.

---

## 2. Problem Statement

The manufacturing control tower needs more than static reporting. A planner should be able to ask questions such as:

- Which high-value orders are most at risk this week?
- Why has revenue at risk increased at the West site?
- Which product families are driving the increase?
- Are strategic customers disproportionately affected?
- How is September demand tracking against forecast?
- Which site and product-family combinations have the largest forecast error?
- What should the planner investigate first?

A Power BI dashboard can answer predesigned questions very well, but users will inevitably ask follow-up questions that were not encoded as visuals. The agent should provide exploratory analysis across a curated business dataset while remaining grounded in real data.

The original preferred architecture used a Fabric Data Agent as the governed data-access layer. Fabric Data Agent currently requires paid F2+ capacity. The demo therefore needs a lower-complexity path that does not require F2 and does not require building a custom NL-to-SQL system.

---

## 3. Product Goal

Create a Foundry-based manufacturing analytical agent that can:

1. Answer natural-language questions using real control-tower data.
2. Perform multi-step exploratory analysis using Python.
3. Investigate anomalies by repeatedly slicing, grouping, joining, and comparing data.
4. Support both late-order-risk and demand-forecast analysis.
5. Keep quantitative answers grounded in supplied analytical snapshots.
6. Remain independent of the developer laptop at runtime.
7. Be publishable behind a stable Foundry endpoint for later integration into Power BI.
8. Avoid F2/Fabric Data Agent as a V1 dependency.

---

## 4. Non-Goals for V1

The V1 will not attempt to:

- Build a general-purpose NL-to-SQL engine.
- Give the model unrestricted access to all Bronze/Silver Lakehouse tables.
- Query OneLake live from built-in Code Interpreter.
- Use Fabric Data Agent before F2 capacity is available.
- Perform write-back actions such as changing an order, releasing a quality hold, or updating a production schedule.
- Provide real-time streaming analytics.
- Automatically receive Power BI page/filter context in the initial build.
- Build a custom Foundry Hosted Agent container or custom Code Interpreter environment unless a hard blocker appears.

---

## 5. V1 Architecture Decision

### 5.1 Selected pattern

```text
                         MICROSOFT FABRIC / ONELAKE
                         Authoritative source of truth
                                  |
                     Silver / Gold Delta tables
                     (Parquet + Delta transaction log)
                                  |
              +-------------------+-------------------+
              |                                       |
              v                                       v
        Power BI semantic/report                Snapshot publisher
        reads governed Gold data                      |
                                                      v
                                          Agent analytical snapshots
                                           CSV + data dictionary
                                                      |
                                                      v
                                        Foundry project file storage
                                                      |
                                                      v
                                          Foundry Code Interpreter
                                        Python sandbox during session
                                                      |
                                                      v
                                           Foundry Prompt Agent
                                                      |
                                                      v
                                            Foundry agent endpoint
                                                      |
                                        [Future Power BI integration]
```

### 5.2 Why this architecture

It preserves a clean separation of concerns:

- **Fabric / OneLake** owns durable business data.
- **Azure ML** owns model training/scoring and prediction production.
- **Fabric Gold** owns business-ready analytical outputs.
- **Foundry Code Interpreter** gives the agent flexible analytical computation.
- **Foundry Prompt Agent** owns conversational reasoning, investigation, explanation, and recommendations.
- **Power BI** remains the primary visual analytics surface.

It also avoids the two undesirable extremes:

- Too restrictive: dozens of hard-coded functions for every possible business question.
- Too complex: agent-generated SQL, schema discovery, SQL validation, retry logic, and join planning.

---

## 6. Data Architecture and Storage

### 6.1 Canonical data: Fabric / OneLake

The source of truth remains the Fabric Lakehouse. Bronze, Silver, and Gold tables are stored as Delta tables in OneLake.

A Delta table physically consists of:

```text
<Table folder>/
  _delta_log/
  part-....parquet
  part-....parquet
  ...
```

The Parquet files therefore remain inside OneLake under Fabric management. They are not copied to a developer laptop and are not replaced by CSV as the enterprise data store.

### 6.2 Azure ML interaction

Azure ML reads the required Fabric tables directly from OneLake using ABFSS paths. The ML pipeline trains and scores the late-order-risk and demand-forecast models and publishes prediction outputs for downstream use.

Target analytical outputs include:

- Late-order-risk predictions.
- Risk bands and model metadata.
- Model score factors / explanations.
- Demand forecast predictions.
- Forecast-vs-actual fields when outcomes become available.

These outputs should ultimately be available in Fabric Gold so Power BI and the agent can originate from the same governed analytical layer.

### 6.3 Agent snapshot layer

The agent should not ingest all 61 Lakehouse tables. Instead, create a deliberately small analytical universe designed for conversational investigation.

Recommended files:

**`agent_order_risk.csv`**
- One row per sales-order line.
- Order/customer/product/site context.
- Late-risk probability and band.
- Order value and quantity exposure.
- Promised date and days remaining.
- Top model score factors.
- Outcome fields when known.

**`agent_order_constraints.csv`**
- One or more current operational constraints associated with an order line.
- Material shortage, supplier delay, capacity pressure, quality hold, logistics issue, or other supported constraint types.
- Constraint severity and selected operational details.

**`agent_demand_forecast.csv`**
- Site x product-family x month analytical grain.
- Forecast quantity.
- Actual quantity when available.
- Forecast error, bias, and model metadata.

**`agent_data_dictionary.md`**
- Business meaning of every important field.
- Join keys.
- Metric definitions.
- Date definitions.
- Known limitations and interpretation rules.

Optional later file:

**`agent_supplier_analysis.csv`**
- Supplier risk/performance summary if supplier analytics becomes part of the demo scope.

### 6.4 Why CSV for the agent

Built-in Foundry Code Interpreter currently supports CSV, JSON, XLSX and several document/code formats, but Parquet is not listed as a supported uploaded file type.

Therefore:

```text
Fabric source of truth       = Delta / Parquet in OneLake
Agent analysis interface     = Curated CSV snapshots
Code Interpreter working dir = Temporary /mnt/data sandbox
```

This is an interface conversion, not a storage redesign.

### 6.5 Where agent files are stored

The uploaded snapshot files live in the Foundry Agent Service file-storage layer.

For the current **Basic setup**, Foundry stores files in secure Microsoft-managed storage associated with the Foundry project.

If the project later moves to **Standard setup**, uploaded files can be stored in organization-owned Azure Storage along with customer-controlled agent resources.

Uploaded project files persist until explicitly deleted. During an analysis session, Code Interpreter makes the relevant files available inside its temporary Python execution environment under paths such as `/mnt/data/...`.

The temporary Code Interpreter sandbox is not the durable system of record.

### 6.6 Snapshot freshness and versioning

Every analytical snapshot must contain or be associated with:

- `data_as_of`
- snapshot generation timestamp
- source Gold table/version where practical
- ML model name/version for prediction fields
- training-data cutoff for model predictions

For the demo, manual or one-command snapshot publication is acceptable. A later production version can schedule publication after Gold tables refresh.

Recommended demo naming pattern:

```text
agent_order_risk_2026-09-28.csv
agent_order_constraints_2026-09-28.csv
agent_demand_forecast_2026-09-28.csv
agent_data_dictionary.md
agent_snapshot_manifest.json
```

The manifest should record the common `data_as_of` timestamp and file IDs used by the active agent version.

---

## 7. Foundry Agent Design

### 7.1 Agent type

Use a **Foundry Prompt Agent**, not a custom Hosted Agent container.

The prompt agent consists of:

- Deployed model: current project deployment can continue to use `analytics-agent-model` / DeepSeek-V4-Flash unless tool compatibility or quality requires a change.
- System instructions.
- Code Interpreter tool.
- Attached analytical snapshot files.
- Optional additional deterministic tools later.

This keeps infrastructure minimal while still allowing the agent to be exposed through Foundry's managed agent endpoint/publishing model.

### 7.2 Role of Code Interpreter

Code Interpreter is the analytical engine available to the agent.

The agent can generate Python such as:

```python
import pandas as pd

risk = pd.read_csv('/mnt/data/...agent_order_risk.csv')

west = risk[
    (risk['site_name'] == 'West') &
    (risk['risk_band'] == 'High')
]

result = (
    west.groupby('product_family')['revenue_at_risk']
        .sum()
        .sort_values(ascending=False)
)
```

The agent may then inspect the result, form a hypothesis, and run another analysis. This iterative loop is the core reason for choosing Code Interpreter.

### 7.3 Analytical loop

```text
User question
    |
    v
Agent interprets business intent
    |
    v
Select relevant snapshot file(s)
    |
    v
Generate Python analysis
    |
    v
Execute in Code Interpreter
    |
    v
Inspect result
    |
    +----> enough evidence? ---- yes ----> synthesize answer
    |
    no
    |
    v
Generate follow-up Python analysis
    |
    v
Repeat until evidence is sufficient
```

This enables the agent to behave like an analyst rather than a collection of canned reports.

### 7.4 Example exploratory flow

User asks:

> Why has revenue at risk increased this month?

Possible agent reasoning flow:

1. Compare current-month versus previous-month revenue at risk by site.
2. Identify the site with the largest increase.
3. Within that site, break exposure down by product family.
4. Identify the dominant product family.
5. Break that group down by customer priority or customer.
6. Inspect current constraints on affected order lines.
7. Return a concise business explanation supported by computed figures.

No dedicated `get_revenue_at_risk_by_site_then_product_then_customer()` function needs to exist beforehand.

---

## 8. Grounding and Business Rules

The agent must be explicitly instructed to follow these rules.

### 8.1 Quantitative grounding

- Do not invent business numbers.
- Use Code Interpreter for numerical claims, ranking, aggregation, comparison, and derived metrics.
- State when the requested answer is not supported by the supplied snapshots.
- Report `data_as_of` when freshness is materially relevant.

### 8.2 Late-order-risk interpretation

The V1 late-risk model predicts the probability that a sales-order line's first physical shipment will occur after the company's promised ship date, or remain unshipped when the promised date passes.

The agent must distinguish:

- **Model risk:** likelihood of late first shipment.
- **Model score factors:** features that influenced the model's score.
- **Current operational constraints:** live/current evidence such as material shortage, supplier delay, production pressure, quality hold, or logistics issue.

The agent must not present model score factors as proven root causes.

### 8.3 Business priority versus model probability

A high model probability is not automatically the highest business priority.

Business priority may also depend on:

- line/order value
- customer priority/service level
- promised date and remaining time
- quantity at risk
- current operational constraint
- recoverability

### 8.4 Forecast interpretation

The agent must distinguish:

- forecast quantity
- actual quantity to date
- complete-period actuals
- partial-period actuals
- forecast error and bias

It must not call a month "below forecast" merely because partial-month actuals are lower than a full-month forecast without a pacing calculation or explicit caveat.

---

## 9. End-to-End Data and Request Flow

### 9.1 Data preparation flow

```text
Raw manufacturing data
        |
        v
Fabric Bronze
        |
        v
Fabric Silver
        |
        +----------------------------+
        |                            |
        v                            v
Azure ML late-risk model      Azure ML forecast model
        |                            |
        +-------------+--------------+
                      |
                      v
                 Fabric Gold
          Business-ready analytics
                      |
          +-----------+------------+
          |                        |
          v                        v
       Power BI              Snapshot publisher
                                   |
                                   v
                         Agent CSV snapshots
                                   |
                                   v
                           Foundry file storage
```

### 9.2 User request flow

```text
User asks business question
        |
        v
Foundry Prompt Agent
        |
        v
Code Interpreter requested
        |
        v
Relevant CSVs mounted into session sandbox
        |
        v
Agent writes/runs Python
        |
        v
Results returned to agent
        |
        v
Optional second/third analytical pass
        |
        v
Grounded business answer
```

---

## 10. Functional Requirements

### FR-1: Exploratory late-order analysis

The agent shall answer exploratory questions across late-order-risk data by site, warehouse, product family, customer, customer type, priority, risk band, order value, quantity, and time period where those fields are available.

### FR-2: Drill-down

The agent shall be able to move from aggregate patterns to specific order lines and explain which orders contribute most to the selected exposure.

### FR-3: Period comparison

The agent shall compare compatible time periods and identify increases, decreases, and concentration changes.

### FR-4: Forecast analysis

The agent shall analyze demand forecast versus actual performance by month, site, and product family.

### FR-5: Cross-domain analysis

Where the curated data supports it, the agent shall combine forecast and late-order-risk outputs to investigate whether demand patterns and execution risk coincide.

### FR-6: Follow-up questions

The agent shall support conversational follow-ups without requiring the user to restate the complete analytical question each time, within the capabilities of the chosen Foundry conversation/invocation path.

### FR-7: Evidence-based answers

Quantitative conclusions shall be generated from Code Interpreter results, not model memory.

### FR-8: Graceful unsupported response

When the snapshots lack required data, the agent shall state what is missing rather than fabricate an answer.

### FR-9: Snapshot awareness

The agent shall be able to report the snapshot `data_as_of` timestamp and model version when asked.

### FR-10: Stable external invocation

The working agent shall be publishable/exposable through Foundry's managed agent endpoint so a later UI can invoke it without running application logic on a developer laptop.

---

## 11. Non-Functional Requirements

### Reliability

- Every numeric claim should be traceable to supplied data or an explicitly described calculation.
- Missing/invalid files must produce a clear failure, not fabricated results.

### Performance

- Agent snapshots should be curated enough to load comfortably into the Code Interpreter session.
- Avoid sending the full historical enterprise Lakehouse when only a few analytical tables are required.

### Maintainability

- Snapshot schema and metric definitions must be documented in `agent_data_dictionary.md`.
- The snapshot publisher should be separate from Foundry prompt logic.
- File names, schema, and business definitions should be version controlled.

### Security

- No database credentials are exposed to the model.
- V1 Code Interpreter receives only curated files required for the manufacturing analytical scope.
- Sensitive columns not required for the demo should be omitted before upload.

### Reproducibility

- Each snapshot should have a `data_as_of` timestamp.
- ML predictions should contain model/version and training-cutoff metadata.
- Demo responses should be reproducible from the same snapshot version.

---

## 12. Licensing and Cost Model

### 12.1 F2 dependency

The V1 described in this PRD does **not** require Fabric Data Agent and therefore does not require F2 for the agent architecture itself.

F2+ becomes relevant when the architecture is upgraded to use Fabric Data Agent for governed natural-language access to Fabric data.

### 12.2 V1 cost components

Expected agent-side costs are primarily:

- Foundry model inference/token usage.
- Code Interpreter sessions.
- Agent/file storage according to the Foundry environment setup.
- Existing Azure ML/Fabric resources used by the broader solution.

Exact prices should be checked against the current Azure pricing pages rather than hard-coded into the design document.

---

## 13. Build Scope: Start Today

The following can begin immediately and does not depend on Power BI embedding or F2.

### Workstream A - Analytical snapshot contract

Define and generate:

1. `agent_order_risk.csv`
2. `agent_order_constraints.csv`
3. `agent_demand_forecast.csv`
4. `agent_data_dictionary.md`
5. `agent_snapshot_manifest.json`

### Workstream B - Foundry agent

1. Enable Code Interpreter on the existing Foundry prompt agent.
2. Upload the first analytical snapshots.
3. Attach the required files/tool configuration.
4. Strengthen system instructions for grounded analysis.
5. Test multi-step Python analysis.
6. Validate unsupported-question behavior.

### Workstream C - Snapshot publisher

Create a small script/process that:

1. Reads the latest Gold analytical outputs.
2. Creates compact agent-facing CSVs.
3. Adds `data_as_of` and model metadata.
4. Validates required columns and row counts.
5. Uploads the files to Foundry.
6. Produces/updates the manifest.

For the demo, this process may be manually triggered. Scheduling is not required.

### Workstream D - Evaluation questions

Create a repeatable set of analytical questions covering:

- risk concentration
- month-over-month change
- high-value/strategic-customer exposure
- site/product-family drill-down
- order-level drill-down
- constraint analysis
- forecast versus actual
- forecast bias/error
- cross-domain investigation
- unsupported/out-of-scope questions

---

## 14. Potential Upgrade: Power BI Dashboard Context

This is explicitly **not required for the initial build**.

Later, embed a **Power Apps visual** inside the Power BI report as the chat surface.

Power BI can pass selected context-aware fields to the Power App through `PowerBIIntegration.Data`. The app can forward that structured context together with the user's question to the Foundry agent.

Potential context payload:

```json
{
  "page": "Late Order Risk",
  "site": "West",
  "month": "2026-09",
  "product_family": "Pumps",
  "risk_band": "High",
  "selected_order_id": "SO123"
}
```

The agent would then have three sources of information:

```text
User question
      +
Power BI context
      +
Agent analytical snapshots
      |
      v
Context-aware analysis
```

### 14.1 Important limitation

The Power Apps visual does not magically understand the full Power BI screen. Only fields deliberately passed into the visual are available through the Power BI integration object.

A simple future implementation can include a disconnected `AgentContext` table with a page/business-area value and page-level filters so the chat knows which business page it is embedded on.

### 14.2 Why this remains an upgrade

The agent's analytical intelligence can be built and tested independently of Power BI. Delaying context integration protects the demo schedule while leaving a clean path to a dashboard-native experience.

---

## 15. Potential Upgrade: Fabric Data Agent

When paid F2+ capacity is available, Fabric Data Agent can become the preferred governed data-access layer.

Future architecture:

```text
Power BI / user
      |
      v
Foundry Agent
      |
      v
Fabric Data Agent
      |
      v
Fabric Lakehouse / Warehouse / Semantic Model
```

This would remove the need to publish snapshot CSVs for many open-ended analytical questions and would provide a more direct governed connection to Fabric.

The outer Foundry business-reasoning layer, instructions, user experience, and Power BI integration can remain conceptually similar.

---

## 16. Demo Acceptance Criteria

The V1 is demo-ready when all of the following are true:

1. A Foundry prompt agent can analyze the uploaded manufacturing snapshots using Code Interpreter.
2. The agent can answer at least 10 predetermined analytical questions correctly.
3. At least 3 of those questions require multi-step analysis rather than a single aggregation.
4. The agent can drill from aggregate site/product results to specific order lines.
5. The agent can compare two periods and explain the primary drivers of change.
6. The agent can analyze forecast versus actual and correctly distinguish partial versus completed periods.
7. The agent refuses or qualifies questions unsupported by the snapshot.
8. Quantitative answers are reproducible from the uploaded files.
9. The agent can report the current `data_as_of` timestamp.
10. The agent can be invoked from a Foundry-managed endpoint independently of the developer laptop.

Power BI chat embedding and dashboard-context awareness are not blockers for V1 acceptance.

---

## 17. Suggested Demo Questions

1. Which site currently has the most revenue at risk?
2. Why has revenue at risk increased compared with the previous period?
3. Which product families are responsible for the increase at the worst-performing site?
4. Are strategic customers disproportionately represented among high-risk orders?
5. Which five order lines should a planner investigate first and why?
6. What current operational constraints are most common among the highest-risk lines?
7. How is September demand tracking against the frozen forecast?
8. Which site/product-family combination has the largest forecast error?
9. Is forecast underestimation concentrated in the same areas that show elevated late-order risk?
10. What data is missing if I ask you to determine the exact financial penalty for late shipment?

---

## 18. Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Snapshot becomes stale | Agent and dashboard show different numbers | Generate from same Gold refresh and include `data_as_of` |
| CSV becomes too large | Slow Code Interpreter analysis | Curate columns/rows and split by analytical domain |
| Agent invents numbers | Loss of trust | Require Code Interpreter for quantitative claims |
| Model explanation confused with root cause | Misleading recommendations | Separate score factors from current operational constraints |
| Partial-month comparisons are misleading | Wrong business interpretation | Encode period-completeness rules in prompt/data dictionary |
| Unsupported question triggers hallucination | Incorrect answer | Require explicit unsupported response |
| File schema changes | Python analysis failures | Validate schema in snapshot publisher and version contracts |
| Power BI integration consumes schedule | Demo risk | Keep dashboard context as post-V1 upgrade |
| F2 unavailable | Fabric Data Agent unavailable | V1 snapshot + Code Interpreter path has no Data Agent dependency |

---

## 19. Open Decisions

Before final implementation, confirm:

1. Exact Gold table/view names that feed each snapshot.
2. Whether current operational constraints are available at order-line grain.
3. Exact calculation used for `revenue_at_risk` in the dashboard and agent.
4. Risk-band thresholds after model validation.
5. How much history the agent needs for period comparisons.
6. Whether supplier analysis is included in the 29 September demo.
7. Whether V1 uses a manually uploaded snapshot or a one-command automated publisher.
8. Which Foundry agent model is used if Code Interpreter/tool compatibility differs from the current DeepSeek deployment.

---

## 20. Implementation Sequence to Protect the Deadline

```text
1. Finalize late-order training dataset and label
2. Train/evaluate late-order model
3. Build September replay predictions
4. Train/evaluate demand forecast model
5. Write business-ready analytical outputs to Gold / export layer
6. Generate agent CSV snapshots
7. Enable Code Interpreter and test Foundry agent
8. Run the 10 demo analytical questions
9. Build/refine Power BI visuals against the same Gold outputs
10. Only if time remains: embed chat UI / pass dashboard context
```

The architecture intentionally keeps Steps 1-8 independent of Power BI chat embedding so agent development can start immediately.

---

## 21. Platform Notes Verified for This PRD

As of 21 September 2026:

- Microsoft Foundry Code Interpreter can write and execute Python iteratively and supports uploaded CSV files. Parquet is not listed among its supported uploaded file types.
- In Foundry Basic agent setup, agent files/state use Microsoft-managed storage. Standard setup can use organization-owned Azure resources for files and other agent state.
- Fabric Data Agent requires paid F2+ capacity (or an eligible Premium capacity).
- Power Apps visual for Power BI can receive context-aware report data through `PowerBIIntegration` for a later dashboard-context integration.
- Foundry agents can be exposed through Foundry's managed agent endpoint/publishing experience for external invocation.

### Microsoft references

1. Code Interpreter: https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/code-interpreter
2. Foundry Agent Service environment setup: https://learn.microsoft.com/en-us/azure/foundry/agents/environment-setup
3. Foundry Agent Service FAQ: https://learn.microsoft.com/en-us/azure/foundry/agents/faq
4. Fabric Data Agent creation/prerequisites: https://learn.microsoft.com/en-us/fabric/data-science/how-to-create-data-agent
5. Fabric Data Agent in Foundry: https://learn.microsoft.com/en-us/fabric/data-science/data-agent-foundry
6. Power Apps visual for Power BI: https://learn.microsoft.com/en-us/power-apps/maker/canvas-apps/powerapps-custom-visual
7. Foundry agent publishing/endpoint documentation: https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/agent-applications

---

## 22. Final V1 Decision

For the 29 September demo, build the manufacturing analytical agent as:

```text
Foundry Prompt Agent
        +
Code Interpreter
        +
Curated CSV analytical snapshots
        +
Fabric / OneLake as the source of truth
```

Do **not** build NL-to-SQL, do **not** make F2/Fabric Data Agent a blocker, and do **not** make Power BI context integration a prerequisite.

The first objective is to prove that the agent can independently explore the manufacturing analytical dataset, calculate reliable answers, investigate follow-up questions, and explain business findings. Dashboard-aware context can then be layered on top without redesigning the core agent.
