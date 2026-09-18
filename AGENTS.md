# Project guidance for coding agents

## Purpose and source of truth

This repository supports a **Microsoft Foundry operations assistant demo** for a manufacturing order-to-cash and inventory control tower. The business question is: **Which customer commitments are at risk, why, what recovery action is worth taking, who must approve it, and did it work?** The intended loop is detect risk, explain cause, recommend recovery, obtain approval, execute, and measure the outcome.

Read `docs/manufacturing_order_workflow_requirement.docx` for the manufacturing workflow and business rules, `docs/PRD-Fabric-AzureML-Foundry.md` for the cross-product architecture, and `data/raw/manufacturing_order_inventory_dataset/README.md` plus `data_dictionary.csv` for the supplied data. If their examples differ, use the **manufacturing order workflow** as the demo domain. The PRD's generic regional sales forecast, campaign history, and customer propensity examples illustrate an architecture; they are not the selected use case or confirmed table contract. Record unresolved differences instead of silently treating illustrative names or metrics as final.

## Scope of this repository

- Prioritize the Foundry agent: its instructions, tool integration, evidence handling, reasoning, responses, and evaluation. Fabric, Power BI, Azure ML, Power Apps, and Power Automate are collaborating parts of the overall demo, not an invitation to implement the entire platform here without a specific task.
- The first useful slice is one plant, one finished-goods warehouse, 10 product families, 20 key suppliers, and orders due within 14 days. Start with sales-order-line risk and a question such as, “What is the lowest-cost recovery plan for the Pune orders due this week?” Make this slice work end to end before expanding scope.
- Treat the supplied CSVs as **synthetic demonstration data**. They live under `data/raw/manufacturing_order_inventory_dataset/` (not `data/raw_data/`). `dataset_summary.json` dates the snapshot to 2026-09-15; use an explicit as-of date for repeatable examples and never imply that a static file is live operational data.
- Current `scripts/` and `src/` code is a personal-account exploration of Foundry model deployment and a prompt agent. `src/tools/business_data.py` returns hard-coded regional sales figures; it is only a grounding stub, not Fabric data or evidence for manufacturing answers. Do not present the current agent as the target integration or its outputs as real business results.

## Target architecture and boundaries

1. Fabric/OneLake owns ingested, standardized, governed business data and prediction tables. Preserve source event grain and status history; downstream consumers use agreed Gold tables and shared definitions.
2. The Power BI semantic model owns metric formulas and relationships. Fabric Data Agent uses the governed tables and/or semantic model to retrieve order populations, KPIs, event evidence, and batch predictions. Validate its retrieval and filters independently before connecting Foundry.
3. Foundry calls the published Fabric Data Agent as its business-data tool. Foundry gathers enough evidence, compares alternatives, explains likely causes, and recommends actions. It must not create a separate direct query path to raw CSVs, Lakehouse tables, the semantic model, or a live Azure ML endpoint as a production substitute for the Fabric Data Agent. A clearly labeled local fixture or mock is acceptable for offline development.
4. Azure ML reads curated Fabric data, scores risk, and returns versioned predictions to Fabric for governed consumption. The first slice emphasizes late-order risk; the broader requirement also names supplier receipt, production completion, and quality risk. Keep training and scoring separate and prevent future-event leakage with prediction-time features and temporal validation.
5. Power Apps handles human review and approval; Power Automate creates and tracks approved tasks and notifications. Foundry may draft a proposed action but must not itself release a quality or credit hold, reschedule production, change a promise date or purchase order, or approve premium freight.

Avoid copying governed data into a second long-lived store just to feed the agent or ML. The PRD describes direct OneLake access for Gold Delta tables and a OneLake datastore for suitable files; confirm actual schemas, permissions, and current Microsoft integration behavior when implementing cloud connectivity.

## Agent behavior to preserve

- For company-specific facts, call the governed business-data tool and use only returned evidence. Never invent orders, quantities, probabilities, costs, impacts, targets, causes, or completed actions. Say what is missing when evidence is incomplete or a tool fails.
- Work at **sales-order-line grain** before aggregating by order, customer, product, supplier, plant, warehouse, or region. Keep facts, model predictions, inferred causes, and proposed actions distinct. Include the population, filters, as-of time, units, and prediction/model version when relevant.
- Investigate the cause before recommending a recovery: material shortage or reservation, supplier receipt, production capacity or completion, quality hold, warehouse/carrier, and commercial or credit exception are different paths. Respect quality holds, expiry, blocked and reserved inventory when discussing available-to-promise.
- For a recommendation, state expected service or revenue benefit, estimated incremental cost, key assumptions, affected orders, and required approver. Rank alternatives only when comparable evidence supports the ranking. Do not claim causation from a correlation or a risk score alone.
- A useful answer has a short business summary, affected KPI/order population, main causes ranked by impact, supporting evidence and filters, proposed actions with impact and cost, and uncertainty or missing data. Make it clear that execution requires human approval.
- Keep an audit path from answer and proposal to source records, prediction timestamp/model version, agent instruction version, and any later human decision and outcome. Do not claim an action improved OTIF, backlog, or cost until a measured post-action event supports it.

## Data and implementation notes

- Use `data_dictionary.csv` for table grain and keys. Main joins span `sales_orders`/`sales_order_lines`, status history, reservations and inventory lots, purchase orders and receipts, production orders and operations, quality events, shipments, invoices, and daily snapshots. Check cardinality and dates before computing a KPI; naive joins can duplicate order-line value.
- Keep metric definitions consistent with the governed semantic model once it exists, especially OTIF, backlog, available-to-promise, revenue at risk, and overdue AR. Do not make up final formulas where the documents leave them open; surface the contract that needs agreement.
- Keep cloud endpoints, resource names, deployment names, tenant/account details, and credentials configurable. The existing personal Azure login and deployment are disposable exploration state; the project account will be configured later. Do not hard-code or commit secrets, `.env`, tokens, or personal account identifiers. Avoid cloud provisioning, deployment, or paid runs unless the task calls for them.
- Prefer small, testable changes. Offline tests should use controlled manufacturing fixtures and verify tool calls, numeric grounding, missing-data behavior, cause/action distinctions, and approval boundaries. For connected tests, compare Fabric Data Agent answers with known source rows and semantic-model measures before judging Foundry's explanation.
- Verify current Microsoft documentation before implementing preview Fabric Data Agent ↔ Foundry APIs, capacity requirements, or SDK-specific code; the draft PRD may be outdated. Keep any local mock explicitly separated from the real integration.

## Demo acceptance path

Demonstrate that a manager can identify open commitments due soon; see risk and cause at order-line level; ask Foundry why a plant's commitments are deteriorating; receive evidence-backed, cost-aware recovery proposals; route a proposal for human approval; and later see the action's outcome and audit history. For the Foundry portion, verify that the agent used the Fabric Data Agent, answered from current governed data, identified uncertainty, and never executed a controlled business change on its own.
