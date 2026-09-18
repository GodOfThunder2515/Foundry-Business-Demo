# Product Requirements Document
## Business Analytics + Agentic Insights on Microsoft Fabric, Azure ML & Microsoft Foundry

**Status:** Draft v1
**Reference material:** Architecture discussion transcript + architecture diagram (`architecture-diagram.png`, included with this document)

---

## 1. Overview

We want to show that data flowing into **Microsoft Fabric** can power three things **using the exact same data, with no copies floating around**:

1. **Power BI dashboards** — "what happened?"
2. **An Azure Machine Learning model** — "what's likely to happen next?"
3. **A Microsoft Foundry AI agent** — "what does it mean, and what should we do about it?"

The core idea driving every decision in this document is:

> **Fabric/OneLake is the single source of truth. Power BI, Azure ML, the Fabric Data Agent, and the Foundry Agent are all different "lenses" looking at the same governed data — none of them keep a private copy.**

This document describes the architecture, the reasoning behind each decision, the build order, and the resources a developer (human or AI coding agent) needs to implement it. It does not introduce any component, tool, or design choice beyond what was discussed and diagrammed.

---

## 2. Goals

- Prove that Power BI, Azure ML and Microsoft Foundry can all work off **one governed copy of the data** sitting in Fabric/OneLake.
- Move beyond a plain BI dashboard by adding a **forecasting layer** (Azure ML) and a **reasoning/insights layer** (Foundry Agent) on top of it.
- Keep the machine learning layer **completely independent of where the raw data originally came from** (file, database, API, etc.), so new data sources can be added later without touching the ML code.
- Make sure the AI agent's answers are **grounded in the same business definitions** used in Power BI (no "dashboard says 17%, agent says 19%" problem).
- Build this in small, testable stages rather than one big bang.

## 3. Non-Goals (explicitly out of scope for this build)

These were discussed and deliberately set aside — do not build them unless a future revision of this document says otherwise:

| Not doing (for now) | Why |
|---|---|
| Foundry Agent calling an Azure ML **real-time endpoint** directly (e.g., "predict this one customer's churn right now") | Adds endpoint deployment, schema management, tool-auth and error handling for little extra demo value. Predictions are produced in batch and read from Fabric instead. |
| Azure ML **Batch Endpoint** | Doesn't support the OneLake datastore directly today; would need an extra ADLS Gen2 + OneLake "shortcut" workaround. A scheduled training/scoring job is simpler and does the same job for now. |
| **Fabric Ontology** | A richer way to model business entities/relationships, but adds complexity without enough added value at this stage. |
| The **"link a Lakehouse table" UI method** in Azure ML Studio | This method physically copies the table into ADLS Gen2, which breaks the "one copy of data" principle. |
| Foundry Agent querying the semantic model or Lakehouse directly | Would create two parallel query paths (Foundry and Fabric Data Agent) that could drift out of sync. Foundry always goes *through* the Fabric Data Agent. |

---

## 4. Glossary (plain language)

| Term | What it actually means here |
|---|---|
| **Fabric** | Microsoft's all-in-one data and analytics platform. Think of it as the place where all your business data lives and gets organized. |
| **OneLake** | The single storage layer underneath Fabric. Every Fabric item (Lakehouse, Warehouse, etc.) stores its files here, in an open format, so different tools can read the same physical data. |
| **Lakehouse** | A Fabric item that stores your tables (in a format called Delta, which is basically an organized, query-friendly version of Parquet files) and raw files side by side. |
| **`/Tables` vs `/Files`** | Inside a Lakehouse, `/Tables` holds structured Delta tables (rows and columns, like a database table). `/Files` holds raw files (Parquet, CSV, model artifacts, etc.). |
| **Bronze / Silver / Gold** | A common way to organize a Lakehouse: Bronze = raw data as it arrived, Silver = cleaned and standardized, Gold = business-ready tables people and tools actually query. |
| **Power BI Semantic Model** | A layer that sits above the raw tables and defines what things *mean* — e.g., "Revenue = SUM(InvoiceValue)". Everyone (dashboards, agents, ML feature docs) should use these same definitions. |
| **Fabric Data Agent** | A Microsoft Fabric feature that lets you ask questions in plain English and get answers from your Fabric data (Lakehouse, Warehouse, or a semantic model). It's good at *retrieving and lightly summarizing* data, not at deep multi-step reasoning. |
| **Microsoft Foundry Agent** | A separate AI agent (built in Microsoft Foundry) that can call other tools — including a Fabric Data Agent — and does the heavier reasoning: comparing numbers, explaining causes, and recommending actions. |
| **ABFSS** | The type of file path (`abfss://...`) used to read Fabric/OneLake data directly from Azure ML, without copying it anywhere. |
| **OneLake Datastore** | A registered connection inside Azure ML that points at a Lakehouse's `/Files` area, so ML jobs can read/write there without copying data. |
| **Data contract** | An agreement that a certain table will always have a certain shape (column names/types), no matter how the underlying source data was ingested. This is what lets Azure ML stay unaffected by ingestion changes. |

---

## 5. High-Level Architecture

This is the architecture as drawn and agreed on (see `architecture-diagram.png`):

```
SOURCE SYSTEMS (Sales / CRM / other business data — CSV, SQL Server, API, etc.)
        │  Ingest (Pipelines / Dataflows / Mirroring / Connectors)
        ▼
MICROSOFT FABRIC — OneLake (single, unified data foundation)
        │
        ├── Lakehouse (Bronze → Silver → Gold Delta tables)
        │        │
        │        ├──► Power BI Semantic Model ──► Power BI (dashboards & reports)
        │        │            │
        │        │            └──► used by ──────────────┐
        │        │                                       │
        │        └──► Azure Machine Learning ─────► Prediction table
        │                (reads Gold tables,             (written back
        │                 trains/scores)                  into the Lakehouse)
        │                                                       │
        └───────────────────────────────────────────────────────┘
                                   │
                                   ▼
                      Fabric Data Agent
        (understands the data: Lakehouse tables + semantic model
         + business terminology/rules; retrieves grounded answers)
                                   │
                                   ▼
                     Microsoft Foundry — Business AI Agent
     (calls the Fabric Data Agent as a tool, reasons over the results,
                explains and recommends — does not query Fabric itself)
                                   │
                                   ▼
                             Business Users
                    (ask questions, get insights, take action)
```

**Key rule driving this whole diagram:** the same physical data in OneLake feeds Power BI, Azure ML, and the agents. Nothing gets exported to a separate copy just to be used by a different tool.

---

## 6. Key Architecture Decisions ("what we chose, and why")

### 6.1 Fabric is the data integration boundary — ML never talks to raw sources
Whether a source is a CSV upload, a SQL Server database, or a CRM/API, Fabric ingests it and standardizes it into Gold tables. Azure ML **only ever reads Fabric's standardized Gold tables** — never the original source systems directly.

- **Why:** if a source changes tomorrow (e.g., a CSV feed is replaced by a live SQL Server connection), Fabric's ingestion changes, but Azure ML and its code stay exactly the same, as long as the agreed Gold table schema doesn't change. This "agreed schema" is the **data contract** between data engineering and ML.

### 6.2 Medallion layering inside the Lakehouse (Bronze → Silver → Gold)
- **Bronze:** raw data, as ingested, with minimal changes.
- **Silver:** cleaned, standardized, joined across sources.
- **Gold:** final business tables (e.g., `customers`, `sales`, `campaign_history`) plus a curated ML feature table (e.g., `customer_ml_features`).

### 6.3 How Azure ML reads Fabric data — no-copy access only
Two supported "no-copy" methods were discussed, and each is used for a different purpose:

| Data shape | Method | Used for |
|---|---|---|
| Structured Delta tables under `/Tables` (our Gold business tables) | **Direct OneLake ABFSS access** from Azure ML compute | Preferred, primary method for reading curated business/feature tables |
| Files under `/Files` (Parquet exports, model artifacts, intermediate files) | **OneLake Datastore** registered in the Azure ML workspace | Useful for ML-specific file exports and artifacts, not for the core business tables |

Explicitly **avoided**: registering a Lakehouse table through the Azure ML Studio UI "link" feature, because Microsoft's own documentation shows that method copies the table into ADLS Gen2 first — which breaks the "one copy of data" principle.

Example path patterns discussed (adapt names to the real workspace/lakehouse):

```
# Direct ABFSS read of a Gold Delta table
abfss://<workspace-guid>@onelake.dfs.fabric.microsoft.com/<lakehouse-guid>/Tables/customer_ml_features

# OneLake datastore path (for /Files, e.g. exports or intermediate artifacts)
azureml://datastores/fabric-onelake/paths/ml/training/customer_features.parquet
```

Illustrative Azure ML job input, so the training script itself never has to know or care where the data came from:

```python
Input(
    type="uri_folder",
    path="azureml://datastores/fabric-onelake/paths/ml/features/",
    mode="ro_mount",
)
```

### 6.4 Predictions are written back into Fabric, not kept inside Azure ML
After training/scoring, Azure ML writes its output (e.g., a sales forecast or a propensity score) back into Fabric as a proper Gold table — for example `sales_forecast` or `customer_propensity_predictions`.

Clean responsibility split:
- **Azure ML's job:** "I predict these values."
- **Fabric's job:** "I store, govern, expose, and integrate those predictions."

Each prediction row should carry metadata so history isn't lost on the next run:

```
forecast_for | generated_at | model_version | training_data_cutoff | prediction | lower_bound | upper_bound
```

Keeping forecast history (instead of overwriting it every run) is what later lets Power BI show "actual vs. current forecast vs. previous forecast vs. forecast error", and lets the agents answer questions like "which region is forecast to miss its target?"

### 6.5 Two layers of "meaning" (grounding), not one
To stop the AI agent from inventing its own definition of business terms, two different layers each hold a different kind of context:

| Layer | Holds | Example |
|---|---|---|
| **Power BI Semantic Model** | Hard analytical definitions: metrics, formulas, relationships, hierarchies | `Gross Margin % = Gross Margin / Revenue` |
| **Fabric Data Agent instructions** | Soft business knowledge: terminology, acronyms, which source to use for which question, business rules | "FY = April–March", "For financial questions, use the Finance semantic model", "'Active customer' = purchased in last 90 days AND no payment overdue > 60 days" |

Both feed into the Fabric Data Agent, which is what the Foundry Agent consults — so there is only **one** governed path from a question to an answer, not two competing ones.

### 6.6 Two-agent hierarchy, with a clear division of labor
The Fabric Data Agent and the Foundry Agent are **not** doing the same job:

| Component | Job |
|---|---|
| **Fabric / OneLake** | Store enterprise data |
| **Power BI Semantic Model** | Define business metrics and relationships |
| **Fabric Data Agent** | Understand the question, retrieve the correct grounded data (light summarization is fine; deep multi-step reasoning is not its job) |
| **Azure ML** | Produce forecasts, classifications, risk scores |
| **Foundry Agent** | Reason across the returned evidence — compare, explain, and recommend actions |

The Foundry Agent **does not need direct access to the semantic model or the Lakehouse**. It only needs the Fabric Data Agent as a tool — the Fabric Data Agent's access to the semantic model is enough for the whole chain to be grounded.

### 6.7 Prediction data reaches the agents the same way any other governed table does
Rather than having the Foundry Agent call an Azure ML endpoint live, the chosen approach ("Option A") is: predictions land in a Fabric table → the Fabric Data Agent is given that table as one of its data sources → the Foundry Agent asks the Fabric Data Agent for it like any other business data. This keeps the agent architecture simple and avoids adding a second, separate integration path (endpoint auth, schemas, tool-calling) for now.

---

## 7. Component Requirements

### 7.1 Data Sources & Ingestion (Fabric)
- Expect **three source systems** feeding the same three business tables, e.g.: a file upload (CSV/Excel), a SQL Server database, and a CRM/API.
- Ingestion method is chosen per source and is data engineering's decision — e.g., Pipelines/Dataflows for files, Mirroring or Pipelines for SQL Server, a connector/Pipeline for the CRM/API.
- **Contract with data engineering:** regardless of ingestion method, the output must be a standardized set of Gold Lakehouse tables (agreed names, columns, and types) and, ideally, one curated ML-ready feature table. Downstream components (ML, agents) never need to know or adjust to the original source.

### 7.2 Fabric Lakehouse (Bronze → Silver → Gold)
Illustrative Gold-layer structure used in the design discussion (final table names to be confirmed with data engineering, but the *shape* below is the agreed pattern):

```
Lakehouse
└── Tables/
    ├── customers
    ├── sales                     (or sales_transactions)
    ├── campaign_history
    ├── customer_ml_features      (curated feature table for Azure ML)
    └── customer_propensity_predictions   (or sales_forecast — ML output written back)
```

### 7.3 Power BI Semantic Model
- Built on top of the Gold tables.
- Holds the analytical definitions the whole solution should agree on: Revenue, Gross Margin %, YoY Growth, Sales Target, Variance to Target, table relationships, date/region/product hierarchies.
- Power BI reports and dashboards consume this semantic model (not the raw tables directly).

### 7.4 Azure Machine Learning
- Trains a simple forecasting/regression-style model (e.g., predicting next month's sales, or a customer propensity/risk score) using the curated Gold table(s) as input — read via direct ABFSS access (for Delta tables) or a OneLake Datastore (for `/Files`-based feature exports).
- A **scoring job** (separate from training) runs the registered model to generate fresh predictions on a schedule.
- Output is written back to Fabric/OneLake, then promoted into a Delta table under `/Tables` — Azure ML does not maintain its own permanent copy of the "final" data.
- Training/scoring code should be written so it only depends on the agreed Gold table schema — never on knowledge of the original source system.

### 7.5 Fabric Data Agent
- Configured with the relevant Gold tables and/or the Power BI Semantic Model as its data source(s).
- Given explicit **instructions**: which semantic model/source to use for which type of question, business terminology and acronyms, query-specific rules, and example questions.
- Scope: question understanding + data retrieval + light conversational summarization. It is **not** expected to do complex multi-step reasoning, correlation analysis, or cross-source recommendations — that is the Foundry Agent's job.
- **Must be tuned and validated on its own, before the Foundry Agent is connected** (see Section 9 and 12).

### 7.6 Microsoft Foundry Agent (Business AI Agent)
- Added as a tool: the (already published) Fabric Data Agent.
- Given instructions describing it as a business analyst, including an explicit investigation workflow, e.g.:
  1. Retrieve the relevant KPIs.
  2. Compare current period with prior period.
  3. Compare actuals against targets.
  4. Examine the forecast where available.
  5. Identify the biggest positive and negative drivers.
  6. Recommend what to investigate next.
  7. Never invent numerical values — always use the Fabric tool for company data.
- Decides on its own, per question, whether it needs to call the Fabric Data Agent tool.
- Produces the final natural-language answer for business users (explanation + recommendation), combining whatever the Fabric Data Agent returned with its own reasoning.

---

## 8. Prediction Write-Back Contract (summary)

```
Azure ML scoring job
    ↓ writes output (Parquet/Delta) to OneLake
Fabric
    ↓ promotes/maintains it as a governed Delta table (e.g. sales_forecast)
    ↓ preserves history across runs (don't overwrite blindly)
Power BI + Fabric Data Agent + Foundry Agent
    ↓ all read this table like any other Gold table
```

---

## 9. Build Sequence (Phased Plan)

### Phase 1 — Minimal proof of concept
1. One Fabric Lakehouse table (e.g., `sales`), a small sample (roughly 1,000–10,000 rows).
2. Power BI: a handful of KPIs (e.g., 4) + a monthly sales chart + a region chart.
3. Azure ML: a simple sales forecasting/regression model trained directly against the Fabric table.
4. Write predictions into a `sales_forecast` table in Fabric.
5. Power BI: add an actual-vs-forecast chart.
6. Fabric Data Agent: configure it with `sales` + `sales_forecast`.
7. Foundry Agent: connect the Fabric Data Agent as a tool, instruct it to act as a business analyst.

### Phase 2 — Realistic multi-source build
Once Phase 1 proves the end-to-end pattern, extend it to the real scenario of **three tables from three different source systems**:
1. Fabric ingestion set up per source (file, SQL Server, API/CRM) → Bronze.
2. Silver: clean, standardize, join into `customers`, `sales`, `campaign_history`.
3. Gold: produce the curated `customer_ml_features` table.
4. Power BI Semantic Model built/extended on the Gold tables.
5. **Configure and thoroughly test the Fabric Data Agent** on plain retrieval questions (see Section 12) — do not proceed until this is reliable.
6. Publish the Fabric Data Agent.
7. Create the Foundry Agent and add the Fabric Data Agent as a tool.
8. Give the Foundry Agent its analytical/business-analyst instructions.
9. Test complex, multi-step business questions on the Foundry Agent (see Section 12).
10. Azure ML training/scoring against the curated Gold table(s), writing predictions back to Fabric as described in Section 8.

**Rule of thumb for the whole sequence:** get the Fabric Data Agent's retrieval accuracy right *before* layering Foundry's reasoning on top. A wrong number wrapped in a well-written explanation is still a wrong answer.

---

## 10. Roles & Responsibilities

| Component | Owns |
|---|---|
| Data engineering | Source ingestion (any method), Bronze/Silver/Gold transformations, maintaining the agreed Gold table schema (the "data contract") |
| Fabric | Storage, governance, and exposure of all business and prediction tables |
| Power BI / semantic modeling | Metric definitions, relationships, hierarchies |
| ML / data science | Model training and scoring code, reading only from agreed Gold tables, writing predictions back in the agreed format |
| Fabric Data Agent configuration | Data source selection, business terminology, query rules, example questions |
| Foundry Agent configuration | Analytical reasoning workflow, recommendation style, tool orchestration instructions |

---

## 11. Prerequisites & Licensing

- The direct **Fabric Data Agent → Microsoft Foundry** integration is currently a **preview** feature.
- It currently requires **Fabric capacity F2 or higher**, or **Power BI Premium P1+ with Fabric enabled**, plus the appropriate Fabric/Foundry permissions.
- **Action:** confirm the target tenant's Fabric capacity before starting work on the agent layer (Fabric Data Agent + Foundry), so this isn't discovered late in the build.

---

## 12. Testing & Acceptance Criteria

### 12.1 Fabric Data Agent — validate before connecting Foundry
For each test question, confirm it picks the correct source, generates the correct query, applies the correct filters/metric, and returns the correct result:
- "What was total revenue last quarter?"
- "What was gross margin by region?"
- "Which products missed their targets?"
- "Show YoY sales growth by region."
- "Which region has the largest negative forecast variance?"

### 12.2 Foundry Agent — validate after the Fabric Data Agent is trustworthy
For each, confirm it called the Fabric Data Agent correctly, gathered enough evidence, reasoned soundly, distinguished facts from inference, and that recommendations are actually backed by the retrieved numbers:
- "Which region should management prioritize and why?"
- "Identify three risks for next quarter."
- "What is driving the decline in margin?"
- "Compare Mumbai and Delhi and recommend where we should allocate additional marketing budget."
- "Give me a management summary for this quarter and identify regions likely to miss next quarter's target."

---

## 13. Risks & Assumptions

- The Fabric Data Agent ↔ Foundry integration is a **preview** feature and may change; re-check Microsoft Learn documentation before/at build time.
- Assumes the three real-world data sources can each be connected to Fabric via a standard connector, pipeline, or mirroring — to be confirmed once the actual source systems are known.
- Assumes the team can define and agree on the Gold table schema ("data contract") with data engineering before ML work starts, so Azure ML code doesn't need rework later.
- Batch/real-time endpoint scenarios (Section 3) are deliberately deferred; revisit only if a genuine real-time prediction need emerges.

---

## 14. Reference Architecture Diagram

`architecture-diagram.png` (included alongside this document) is the visual reference this PRD is based on. It shows the same flow described in Section 5: source systems → Fabric (Lakehouse/OneLake) → Power BI and Azure ML in parallel off the same data → predictions written back to the Lakehouse → Fabric Data Agent → Microsoft Foundry Business AI Agent → business users.

---

## 15. References & Resources

Use these while implementing — they are the primary Microsoft Learn sources behind the decisions in this document.

**Fabric & OneLake fundamentals**
- OneLake overview — https://learn.microsoft.com/en-us/fabric/onelake/onelake-overview
- How to connect to OneLake (access API) — https://learn.microsoft.com/en-us/fabric/onelake/onelake-access-api
- Medallion Lakehouse architecture in Fabric (Bronze/Silver/Gold) — https://learn.microsoft.com/en-us/fabric/onelake/onelake-medallion-lakehouse-architecture
- Data ingestion options for a Lakehouse — https://learn.microsoft.com/en-us/fabric/data-engineering/load-data-lakehouse
- Modern Data Warehouse Medallion Architecture (Azure Architecture Center) — https://learn.microsoft.com/en-us/azure/architecture/databases/architecture/dataops-mdw

**Azure ML ↔ OneLake integration**
- Integrate OneLake with Azure Machine Learning — https://learn.microsoft.com/en-us/fabric/onelake/onelake-azure-machine-learning

**Semantic layer**
- Power BI semantic models in Fabric — https://learn.microsoft.com/en-us/fabric/data-warehouse/model-default-power-bi-dataset
- Semantic Link overview (bridges semantic models and Data Science/ML) — https://learn.microsoft.com/en-us/fabric/data-science/semantic-link-overview
- Analyze and train data in Microsoft Fabric — https://learn.microsoft.com/en-us/fabric/fundamentals/analyze-train-data

**Fabric Data Agent**
- Create a Fabric data agent — https://learn.microsoft.com/en-us/fabric/data-science/how-to-create-data-agent
- Data agent configurations (instructions, terminology, rules) — https://learn.microsoft.com/en-us/fabric/data-science/data-agent-configurations
- Fabric data agent runtime — https://learn.microsoft.com/en-us/fabric/data-science/data-agent-runtime

**Foundry integration**
- Consume a data agent in Microsoft Foundry (preview) — https://learn.microsoft.com/en-us/fabric/data-science/data-agent-foundry
- Consume Fabric data agent from Microsoft Foundry via Fabric IQ (preview) — https://learn.microsoft.com/en-us/fabric/data-science/data-agent-foundry-fabric-iq
- Use the Microsoft Fabric data agent with Foundry agents — https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/fabric

---

*End of document.*
