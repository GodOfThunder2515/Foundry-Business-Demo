The data is a synthetic manufacturing order-to-cash and inventory control tower for eight Indian plants, as of **Tuesday 2026-09-15**. The manager's daily question is: which customer commitments are at risk, why, which recovery is worth taking, and who must approve it.

## Which population to use

| Question is about | Population | Source |
|---|---|---|
| Risk, likelihood of lateness, "most at risk", intervention priority, model drivers | Active scored lines: `operational_queue_status` ∈ {OPEN_NOT_YET_DUE, OVERDUE_NOT_SHIPPED} | `late_order_risk` (lines ordered 1–15 Sep 2026, five finished-good families) |
| Backlog, **order holds (credit, customer, quality, material)**, commitment value, customers or products beyond the scored set | Active lines: `order_status` ∈ {open, on_hold, partially_shipped} with promised date in the default horizon | `fact_sales` (not the risk table, which covers only orders placed 1–15 Sep) |
| Shipping performance, on-time, carriers | Shipment lines by `actual_ship_date_key` | `fact_shipments` |
| Stock position, available-to-promise, transfers | Current lots, with no date filter | `fact_inventory_lots` |

The two commitment sources overlap only partly, because the risk table covers only lines ordered 1–15 Sep. Do not mix their counts in one figure. Name the population in the footnote, for example "scored lines ordered 1–15 Sep" or "all active sales lines".

## Business concepts

- **Plant / site / location** ("Pune", "the Nashik plant"): the site_id, never the customer's city. S001 Pune, S002 Nashik, S003 Ahmedabad, S004 Bengaluru, S005 Hyderabad, S006 Delhi, S007 Kolkata, S008 Indore. `late_order_risk.site_id` has it directly; for `fact_sales`, join warehouse_key → dim_warehouse.site_id.
- **At risk / likely late**: `predicted_late_flag = 1`, which is the same as late_probability ≥ decision_threshold (≈ 0.495). "High risk" is late_probability ≥ 0.70.
- **Priority for action**: intervention_priority_score and its band (Critical > High > Medium > Low). Use it for "act on first", "which lines matter most", and planner shortlists. A shortlist ranks the at-risk lines (predicted_late_flag = 1) by this score. Use late_probability for "most likely to be late". Break ties by the other score, then promised date (earliest first), then sales_order_line_id, so that "next 10" pages stay consistent.
- **Revenue at risk**: sum of line_value for at-risk lines only (predicted_late_flag = 1), the full commercial value exposed. The value of all lines in scope, flagged or not, is **value due** ("value due this week"), and is never called revenue at risk. When both matter, write "₹X due, of which ₹Y is at risk". **Expected value at risk**: sum of expected_line_value_at_risk (probability-weighted; a planning estimate, not a loss). Lead with revenue at risk; add expected value when it helps.
- **Backlog / backordered value**: active fact_sales lines with backordered_qty > 0. Backordered value = line_value × backordered_qty ÷ ordered_qty.
- **Overdue commitment**: active line whose promised date is before 2026-09-15 (OVERDUE_NOT_SHIPPED in the risk table).
- **Available stock / available-to-promise**: available_qty on `released` lots not expired at 2026-09-15. Stock that is quality_hold, expired or blocked is not available.
- **Transfer candidate**: available stock of the same product at another warehouse (finished goods are stocked in both warehouse types). Compare it with the backordered quantity at the short warehouse.
- **On-time shipping (OTD)**: share of shipment lines with otd_flag = Y (count-based). This is the delivery KPI to use. For OTIF, use `fact_operations_snapshot.otif_pct`; line-level short_ship_qty is positive on 99% of shipment lines, so it cannot distinguish in-full shipments.
- **Supplier late receipt**: a PO line received after promised_receipt_date_key, or still open past it. `late_risk_flag = Y` is the procurement system's own risk flag.
- **Overdue AR**: fact_finance rows with due_date < 2026-09-15 and outstanding_amount > 0. Sum outstanding_amount, not calculated_outstanding_amount. In the answer, say "invoices past due with an unpaid balance".
- **Quality hold**: two different things; report both separately. (1) Order-level: an active line with hold_reason = quality_block, which is a direct block on that order. (2) Stock-level: lots with quality_status = quality_hold; their whole on_hand_qty is unavailable until disposition (blocked_qty only records the failed portion).
- **Blocked by quality-held stock**: a line is blocked only if released available stock of that product at its warehouse is less than its backordered quantity AND the quality-held on-hand stock there would cover the gap. Lines with enough released stock already are an allocation or picking issue, not a quality issue.
- **Commercial hold**: fact_sales.hold_reason credit_limit or customer_request (material_shortage and quality_block are operational holds). In the answer, say "credit-limit or customer-requested holds". In the risk package, evidence_code COMMERCIAL_HOLD covers every order hold; read the reason in evidence_description.
- **Strategic customer**: customer service_level = strategic.

## Time rules

- **As-of date**: 2026-09-15. Treat later dates in any file as beyond the snapshot.
- **This week / next 7 days**: promised date 15–21 Sep inclusive. **Next 14 days**: 15–29 Sep inclusive, which is exactly `within_14_day_window = True` among active risk lines. **Next 30 days**: 15 Sep–14 Oct.
- **Default commitment horizon** for fact_sales (when no window is given): promised dates 2026-06-01 to 2026-09-30. fact_sales holds about 100,000 older "active" lines back to 2024, so never report active totals without a window. If older overdue lines are material, mention them in a single sentence.
- **Months**: June, July and August are complete; September is partial (1–15). Compare September 1–15 with August 1–15, or use daily rates or percentages. Never compare partial September totals with a full month.
- **Which date to filter on**: commitments use the promised ship date; shipments use actual_ship_date_key; procurement uses promised_receipt_date_key (actual_receipt_date_key for outcomes); quality uses inspection or opened date; finance uses due_date; operations snapshots use snapshot_date_key ≤ 20260915. Inventory lots are current state and take no date filter.
- **Model timing**: scores are a replay by the logistic regression model v1 (logistic_regression in the data), trained to 2026-08-31 and generated 2026-09-23 for the 15 Sep snapshot. Say "replay scores" once, in the footnote, unless the question is about the model itself (see playbook 8).

## Evidence types — keep them separate

Recorded fact (a transaction or status) → model prediction (a probability) → model driver (why the model scored it, not a cause) → operational signal (rule-derived condition linked to the line) → your inference (label it) → proposed action (not executed). Upstream data (procurement, reservations, quality, operations) links to customer lines only through product, warehouse, site and time, so call such findings "associated", not the cause.

## Recovery paths and approvers

| Path | Typical signal | Possible actions | Approver |
|---|---|---|---|
| Inventory | LOW_ALLOCATION_RATIO, POSSIBLE_INVENTORY_SHORTAGE, released stock elsewhere | Reallocate stock, inter-warehouse transfer, partial shipment | Warehouse / site operations manager (partial shipment: sales with customer consent) |
| Production | PRODUCT_SITE_CAPACITY_PRESSURE, production_delay exceptions | Resequence production, overtime, alternate site | Production planner / plant manager |
| Supply | Late or open PO lines, supplier risk tier C | Expedite PO, alternate supplier | Procurement manager / buyer |
| Quality | QUALITY_HELD_STOCK, quality_block holds, recent NCs for the product | Prioritise disposition review | Quality manager |
| Logistics | carrier_capacity exceptions, low carrier OTD | Switch carrier, upgrade to express (premium freight) | Logistics manager, plus finance for premium freight |
| Commercial | COMMERCIAL_HOLD, credit_limit or customer_request holds | Credit review, customer re-confirmation, re-promise | Credit controller / finance; sales manager for promise changes |

The agent only proposes actions. Hold releases, schedule or promise changes, PO changes and premium freight need human approval and are executed outside the agent.

## Data quirks (do not report as findings)

fact_sales.line_status and backorder_flag are nearly all "backordered"/"Y". fact_shipments.line_status is nearly all "short_shipped", and short_ship_qty > 0 on 99% of lines. On quality-hold lots, available_qty is close to on_hand_qty and blocked_qty is small; treat the whole lot as unavailable (see "Blocked by quality-held stock"). The "units blocked" figure in QUALITY_HELD_STOCK descriptions is blocked_qty only. 94% of material reservations are "short". fact_operations_snapshot covers only September 2026. Base insights on the reliable fields named above, not on these flags.
