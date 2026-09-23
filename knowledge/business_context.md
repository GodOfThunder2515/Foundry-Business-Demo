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

## Measures

- Backlog and revenue at risk start from active sales-order lines and their remaining/backordered quantities and line value. State the exact status and date filters.
- Available-to-promise must not count blocked, quality-held, expired, or reserved stock as freely available when the required fields exist.
- OTIF and on-time shipping use shipment outcomes at the appropriate shipment/order-line grain. State whether the measure is a count- or quantity-based interpretation if the semantic-model contract is not available.
- Overdue AR uses due date, receipt status, and outstanding amount as of the snapshot.
- Never sum dimension attributes or multiply measures through one-to-many joins.

## Recovery and approvals

Possible proposals include inventory reallocation, warehouse transfer, shipment-service change, production reprioritization, supplier escalation, alternate supply, or commercial review. A recommendation must explain benefit, cost evidence or its absence, assumptions, affected commitments, and approval. Quality/credit hold release, schedule or promise changes, purchase-order changes, and premium freight are controlled actions and cannot be executed by the agent.
