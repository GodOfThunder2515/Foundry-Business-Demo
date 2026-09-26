# Foundry Agent Dataset Decision

## Decision status

Accepted for the first manufacturing control-tower agent demo.

This decision defines the data exposed to the Microsoft Foundry agent, the default analytical period, and the boundary between full-data Python execution and model-visible results.

## Decision summary

The agent will analyze the existing manufacturing Gold snapshot without adding, reshaping, or denormalizing Gold tables.

- Source snapshot: `data/gold_snapshots/epic_soca_6rn73kkx4n/named-outputs/snapshot/`
- Data as-of date: `2026-09-15`
- Default analytical period: June through September 2026
- Execution method: Foundry Code Interpreter using Python
- Model-visible result cap: 15 rows per returned result
- Golden evaluation set: approximately 15 to 20 representative questions
- Supported behavior: open-ended analysis within the supplied manufacturing dataset and documented business rules; the golden questions are tests, not a fixed question menu

The complete working data remains available to Python. Raw rows are not inserted into the language-model prompt or conversation context. Only capped summaries, aggregates, warnings, and ranked records are returned to the model.

## Source-of-truth boundaries

The existing Gold snapshot remains unchanged. No additional agent-specific Gold tables, views, bridge tables, or consolidated `agent_*` tables will be created for this demo.

This decision supersedes the agent-specific snapshot recommendation in Section 6.3 of `Manufacturing_Control_Tower_Foundry_Agent_PRD.md`, including the proposed `agent_order_risk`, `agent_order_constraints`, and similar derived files.

Handcrafted agent instructions and knowledge may describe the existing data, joins, calculations, evidence levels, and business rules. They must not invent transactions, relationships, actions, costs, or outcomes that are absent from the data.

## Dataset included

The agent may use all 16 tables in the current Gold snapshot.

### Dimensions

| Table | Agent use |
|---|---|
| `dim_customer` | Customer identity, type, location, service level, credit limit, payment terms, and account status. |
| `dim_date` | Calendar attributes only where the date key is covered by the dimension. Future commitment keys after `2026-09-15` must be parsed directly as `yyyyMMdd`. |
| `dim_product` | Product, family, cost, price, lead time, stock policy, unit of measure, and make-or-buy classification. |
| `dim_region` | Available for inspection, but not used for quantitative attribution until a documented relationship to another table exists. |
| `dim_supplier` | Supplier identity, location, delivery baseline, quality baseline, and risk tier. |
| `dim_warehouse` | Warehouse, site, type, capacity, and active status. Joins must use `warehouse_key`, not warehouse code alone. |

### Facts

| Table | Agent use |
|---|---|
| `fact_sales` | Central sales-order-line population, commitments, status, quantities, value, priority, holds, and backlog. Analysis starts at `sales_order_line_id` grain. |
| `fact_shipments` | Shipment and delivery outcomes, carrier, service level, short shipment, freight allocation, and logistics exceptions. Joins to sales use `sales_order_line_id`. |
| `fact_inventory_lots` | Current lot-level on-hand, available, blocked, quality-held, expiry, warehouse, and cost position. |
| `fact_inventory_transactions` | Inventory movement history, reason codes, reference records, quantities, and inventory value changes. |
| `fact_material_reservations` | Production-order material requirements, reserved quantity, issued quantity, shortage quantity, and fill percentage. |
| `fact_procurement` | Purchase-order-line supplier commitments, expected receipts, pending quantities, late-risk flags, receipt progress, quality holds, and cost. |
| `fact_quality_inspections` | Production inspection results, failed quantities, defect rates, and quality holds. |
| `fact_quality_nonconformances` | Nonconformance severity, category, recorded root-cause category, disposition, affected quantity, and quality cost. |
| `fact_finance` | Invoice, receipt, due-date, outstanding-balance, freight, and overdue-exposure analysis. |
| `fact_operations_snapshot` | Available site-level daily service, backlog, production, inventory, quality, supplier, and finance KPIs. The current snapshot contains approximately 30 days, not four complete months. |

## Model prediction inputs

Four Azure Machine Learning prediction outputs are expected as agent inputs when they become available:

1. Late-order risk at sales-order-line grain.
2. Supplier-receipt risk at purchase-order-line grain.
3. Production-completion risk at production-order grain.
4. Quality risk at the scored entity grain.

Their physical filenames and schemas will be recorded after they exist. Each output must expose its entity key, prediction timestamp, model name, model version, probability, risk band, reason codes, and actual outcome when available.

These prediction outputs do not authorize the agent to describe a model reason code as a proven operational cause. Model risk, model drivers, current operational evidence, and confirmed recorded causes must remain distinct.

## Time-window decision

The files are not physically reduced to a 14-day snapshot. Python may analyze the complete existing Gold files.

The default business-analysis horizon is June through September 2026:

- Historical event period: `2026-06-01` through the as-of date, `2026-09-15`.
- Commitment period: promised dates from `2026-06-01` through `2026-09-30`.
- Current operational views: overdue active commitments and commitments due in the next 7, 14, or 30 days, depending on the question.
- Current-state tables such as inventory lots: use the current snapshot rather than applying an arbitrary four-month filter.
- Open or unresolved records: retain them when they affect the selected commitment population, even if their creation date predates June.
- Prediction analysis: filter by prediction timestamp and report the model version and run used.

June, July, and August are complete comparison months. September is a partial current month at the `2026-09-15` snapshot. The agent must not compare partial September actuals with complete prior months without an explicit partial-period qualification or pacing calculation.

The four-month `fact_sales` commitment population contains 45,474 order lines across 17,299 orders. This volume is small for Python analysis and does not need to enter the model context directly.

## Table-specific date rules

The agent must use the business date appropriate to each question rather than applying one global date field:

| Subject | Primary date fields |
|---|---|
| Customer commitment | Promised ship date; requested ship or delivery date when explicitly requested. |
| Shipment performance | Planned ship or delivery date and actual ship or delivery date. |
| Procurement | Expected or promised receipt date; actual receipt date for outcomes. |
| Material availability | Required date plus current reservation status. |
| Quality | Inspection date or nonconformance opened and closure dates. |
| Finance | Invoice date, due date, and receipt date. |
| Inventory movement | Transaction timestamp. |
| Operational KPI | Snapshot date. |
| Model prediction | Prediction timestamp and prediction horizon. |

`dim_date` currently ends on `2026-09-15`, while fact tables contain later date keys. The agent must parse uncovered integer date keys directly using `yyyyMMdd`; it must not silently drop future commitments through an inner join to `dim_date`.

## Join and evidence rules

1. Start customer-commitment analysis at `sales_order_line_id` grain and aggregate only after line-level measures are established.
2. Join facts to dimensions using surrogate keys such as `customer_key`, `product_key`, `warehouse_key`, and `supplier_key`.
3. Join shipments to sales using `sales_order_line_id`.
4. Do not join procurement directly to a finished-goods sales line and present the result as a confirmed component cause unless the supplied data provides a valid relationship.
5. Material reservations and quality facts may be analyzed by their recorded production-order, product, warehouse, lot, and date fields. Where no exact order-line relationship exists, describe the result as an associated operational signal rather than a confirmed cause for that customer line.
6. Do not use `dim_region` for attribution until a documented relationship exists.
7. Prevent one-to-many joins from multiplying order quantity, order value, invoice value, inventory quantity, or prediction counts. Aggregate child facts to the required grain before joining.
8. Distinguish recorded facts, model predictions, analytical inferences, and proposed actions in every answer.

## Code Interpreter and context boundary

Code Interpreter may read and analyze every relevant row in the uploaded files. File contents are working data for Python; they are not prompt context.

Only a controlled result object may be returned from an analysis:

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

### Model-visible limits

- Maximum rows in one returned result: 15.
- Maximum detailed order lines: 10 unless the user explicitly requests another page.
- Maximum columns in one returned table: 12.
- Maximum ranked groups or categories: 15.
- Always return the full matched-row count even when details are truncated.
- Sort using a documented business rule before truncation; never return an arbitrary first 15 rows.
- Never print an entire dataframe, CSV, Parquet file, or unbounded list.
- Keep full intermediate dataframes and calculations inside Python.
- Save large optional results as temporary artifacts rather than inserting them into the model-visible output.
- Support explicit pagination for follow-ups such as “show the next 10.”

The default ranking for at-risk commitments is risk probability or band, then business priority, promised date urgency, line value, and backordered quantity. A question may specify a different ranking.

A prompt instruction alone is not treated as a technical hard limit. The V1 analysis helper or orchestration boundary must apply the row and column caps before returning a result to the agent. Tests must reject uncapped outputs.

## File-format decision

The V1 connected path uses the existing Gold CSV exports because CSV upload and Code Interpreter execution have already passed the repository smoke test.

The equivalent Parquet files remain available locally and are preferable for efficient local profiling. They are not the V1 Foundry upload contract until a separate upload-and-read smoke test confirms that the deployed Foundry Code Interpreter accepts them.

This format decision changes only the temporary agent interface. It does not change the Gold source of truth.

## Agent behavior

The agent is specialized for this manufacturing dataset and workflow, but it is not restricted to exact golden-question wording.

Handcrafted instructions will define:

- table grain and supported relationships;
- metric and filter rules;
- business date selection;
- safe aggregation patterns;
- evidence and uncertainty labels;
- human-approval boundaries;
- the required answer structure.

The agent may answer other dataset-related questions by applying those rules. It must qualify or refuse requests that cannot be supported by the existing tables.

## Golden evaluation set

Approximately 15 to 20 questions will cover:

- commitment population and risk prioritization;
- plant, warehouse, product, customer, and supplier comparisons;
- material, supplier, production, quality, logistics, and commercial signals;
- inventory availability and transfer opportunities;
- shipment and OTIF outcomes;
- finance and credit exposure;
- current-period versus prior-period analysis;
- model prediction interpretation;
- recovery recommendations and approval boundaries;
- data limitations and unsupported claims.

At least several questions must require multi-step Python analysis and drill from an aggregate result to supporting order lines. Rephrased and adjacent questions must also be tested to confirm that the agent applies dataset rules rather than memorizing answers.

## Acceptance checks

The dataset decision is implemented correctly when:

1. The existing Gold source files remain unchanged.
2. No agent-specific Gold table or denormalized replacement is introduced.
3. Python can analyze the complete selected population.
4. Model-visible results never exceed the defined row and column caps.
5. Every quantitative answer records filters, population size, and `data_as_of`.
6. September comparisons are identified as partial-period comparisons where applicable.
7. Future date keys are not lost because of the truncated date dimension.
8. One-to-many joins do not duplicate business measures.
9. The agent distinguishes facts, predictions, inferences, and proposals.
10. The agent answers the golden set reproducibly and handles reasonable adjacent questions using the same rules.

## Explicitly deferred

- Fabric Data Agent integration while the required Fabric capacity is unavailable.
- New agent-specific Gold tables or views.
- A generalized natural-language-to-SQL layer.
- Automatic execution of recommended business changes.
- Treating Power BI, Power Apps, and Power Automate completion as prerequisites for validating Foundry data analysis.

## References

- `docs/manufacturing_order_workflow_requirement.docx`
- `docs/Manufacturing_Control_Tower_Foundry_Agent_PRD.md`
- `data/gold_snapshots/epic_soca_6rn73kkx4n/named-outputs/snapshot/gold_snapshot_manifest.json`
- `data/raw/manufacturing_order_inventory_dataset/data_dictionary.csv`
- `scripts/validate_code_interpreter.py`
