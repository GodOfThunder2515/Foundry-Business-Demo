The snapshot represents a synthetic manufacturing order-to-cash and inventory control tower as of **2026-09-15**. The business objective is to identify customer commitments at risk, explain supported causes or associated signals, compare recovery actions, identify required approval, and later measure the outcome.

## Operating flow

Customer demand begins at sales-order-line grain. Warehouses allocate and ship finished goods; inventory lots describe the current recovery position. Procurement, material reservations, operational snapshots, and quality events describe upstream conditions, but a signal is a confirmed customer-line cause only when the catalog documents a valid relationship. Finance adds invoice, receipt, overdue exposure, and credit context.

## Time rules

- Default history: 2026-06-01 through 2026-09-15.
- Default commitment horizon: promised dates from 2026-06-01 through 2026-09-30.
- Current views: overdue active commitments and those due in 7, 14, or 30 days.
- June, July, and August are complete months. September is partial through 2026-09-15.
- Current inventory uses the available snapshot rather than an arbitrary four-month filter.

## Evidence levels

1. **Recorded fact:** a transaction, status, hold, event, or current snapshot value.
2. **Prediction:** a versioned probability or band at its scored entity and timestamp.
3. **Model reason code:** an explanation of model contribution, not proven causation.
4. **Analytical inference:** a clearly labelled interpretation supported by facts.
5. **Proposal:** an unexecuted recovery option requiring human review.

## Late-order risk replay

The four BI risk tables form one late-order model package. `late_order_risk` contains line-level scores from `logistic_regression:v1`, trained through 2026-08-31 and replayed for the 2026-09-15 business snapshot. The files were generated on 2026-09-23, so describe them as replay predictions rather than scores available live on September 15.

- `late_probability` is the estimated probability of late first shipment.
- `intervention_priority_score` combines risk with value, customer service level, and promise urgency to prioritize attention; it is not a probability.
- `expected_line_value_at_risk` is model-derived expected exposure, not confirmed loss.
- Model factors explain what moved a score. Operational-evidence rows describe rule-derived conditions. Neither alone proves causation.
- Outcome and evaluation fields—including actual ship date, delay, final outcome, and true/false-positive result—are hindsight fields. Do not use them in a forward-looking answer as of 2026-09-15.

## Measures

- Backlog and revenue at risk start from active sales-order lines and their remaining/backordered quantities and line value. State the exact status and date filters.
- Available-to-promise must not count blocked, quality-held, expired, or reserved stock as freely available when the required fields exist.
- OTIF and on-time shipping use shipment outcomes at the appropriate shipment/order-line grain. State whether the measure is a count- or quantity-based interpretation if the semantic-model contract is not available.
- Finance exposure uses the recorded `fact_finance.outstanding_amount` column by default. Treat `calculated_outstanding_amount` as a reconciliation signal, not a substitute measure. For this snapshot, overdue AR means `due_date < 2026-09-15` and `outstanding_amount > 0`; count those invoice rows and sum their `outstanding_amount`.
- Never sum dimension attributes or multiply measures through one-to-many joins.

## Recovery and approvals

Possible proposals include inventory reallocation, warehouse transfer, shipment-service change, production reprioritization, supplier escalation, alternate supply, or commercial review. A recommendation must explain benefit, cost evidence or its absence, assumptions, affected commitments, and approval. Quality/credit hold release, schedule or promise changes, purchase-order changes, and premium freight are controlled actions and cannot be executed by the agent.
