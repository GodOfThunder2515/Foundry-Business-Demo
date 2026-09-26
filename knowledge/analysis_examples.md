These are methods, not answers. Adapt them to the question, combine them when a question spans several, and apply the same thinking to questions not listed here. Always compute before concluding, and always look for the one or two findings a manager would not have seen in a dashboard.

Linking tables: `late_order_risk` joins one-to-one to `fact_sales` on sales_order_line_id. Use that join to get product_key, warehouse_key, backordered_qty, allocated_qty, hold_reason and priority for scored lines. Map site_id and warehouse_id to warehouse_key through `dim_warehouse`.

## 1. Risk overview: "Which commitments are most at risk?"
1. Population: active scored lines in the requested window (default: next 14 days).
2. Size: lines, orders, at-risk lines (predicted_late_flag = 1), revenue at risk (at-risk lines only), expected value at risk.
3. Concentration: group by site_id and product_family. Compare each group's share of revenue at risk with its share of lines, and flag groups that are over-represented. Check whether a few customers or orders dominate.
4. Why: count evidence_code across the at-risk lines (as a share of lines with any signal) to see which recovery paths dominate. Summarise the top INCREASES_RISK model drivers in business words.
5. Lines: show the top 10. Rank by late_probability for "most likely late", or by intervention_priority_score for "where to act". Point out if the two rankings pick very different lines, for example high probability but tiny value.
6. Next steps: map the dominant signals to recovery paths and owners.

## 2. Plant diagnosis: "Why are Pune's commitments at risk / deteriorating?"
1. Compare the site with the network: at-risk rate, revenue-at-risk share against line share, and average late_probability.
2. Signal mix: compare the site's evidence_code shares with the network average. The over-indexed codes are the story.
3. Operations trend: in fact_operations_snapshot, compare the site's production_attainment_pct, otif_pct, on_time_ship_pct, backorder_lines and quality_hold_qty for 1–7 Sep against 8–15 Sep, and against the network.
4. Shipment history: on-time rate (otd_flag) for the site's warehouses, 1–15 Aug against 1–15 Sep, split by exception_code.
5. Model context: the site's row in late_order_model_metrics (quote its sample size).
6. Conclude with the two or three strongest explanations, labelled as recorded condition, signal or association, and what to do about each.
"Deteriorating" needs a comparison. If a metric has no comparable prior period, say so in one line.

## 3. Prioritisation: "Which lines should planners act on first?"
Rank by intervention_priority_score. For each shown line, give the main operational signal (the highest-severity evidence_code, or "no signal" if none) so the planner knows what to check. Note the value, priority and customer service mix of the shortlist, and whether one order or customer accounts for several lines (fixing one order clears several lines).

## 4. Recovery plan and cost: "What is the lowest-cost recovery plan for X?"
The headline states the revenue at risk the plan protects (flagged-late lines only), so it matches the figure the user saw in the risk overview. Never size the plan by backorder value or by all lines due.
1. The plan's population is **only the flagged-late lines** in scope (for example, the site's lines due this week with predicted_late_flag = 1). Lines not flagged late are not being rescued; mention their count and value due once, in the scope line. Classify each flagged-late line by its dominant signal into a recovery path.
2. For each path, give the lines, revenue protected (the line_value of those flagged-late lines) and the candidate action. The path totals add up to the revenue at risk, never to the value of all lines due. Label the table's value column "Revenue at risk".
   - Inventory: check released, unexpired available_qty at other finished-goods warehouses for the same product (see playbook 5).
   - Logistics: compare allocated_freight_cost per shipped unit and on-time rate by service_level over recent shipments before proposing express. The benefit of express is only the gain in on-time rate over standard seen in those shipments; never assume express fixes a delay, and never compute a return on freight spend from revenue at risk. If express is not more on time in the data, recommend against premium freight as the default and say so as a headline finding.
   - Production: site attainment and capacity-pressure signals point to resequencing. There is no overtime cost in the data.
   - Commercial: credit or customer holds need a credit review. The cost is the exposure, not an outlay.
3. Rank paths by revenue protected per unit of cost where cost exists. Otherwise rank by revenue protected, and say the cost ranking is incomplete. Never call an option "lowest cost" without comparable costs.
4. Give owners and approvers from the approvals table, and state that execution needs approval.

## 5. Inventory transfer / available-to-promise
For active backordered lines (in the requested window), total the backordered_qty needed by product_key and warehouse_key. Take free stock (released, unexpired available_qty) by product_key and warehouse_key across all warehouses, because in this data finished goods are stocked and shipped from both warehouse types.
1. Check the line's own warehouse first. Needs already covered by free stock at the same warehouse are not a transfer case: the stock is there but not allocated or picked, so the action is allocation or release (warehouse or site operations). Report how much of the need and value falls in this group, because it is often most of it.
2. Only for needs short locally, match the gap to surplus at other warehouses for the same product. Report which needs could be fully or partly covered, from where, and the value protected, and name stock that exists but is blocked (quality_hold or expired) as a separate lever. Do not double-allocate the same surplus.

## 6. Holds blocking orders: credit, customer, quality
Hold questions are analytical even when phrased "how much": use the full layout (split by hold reason, where the value concentrates, credit context, approver), never a one-line total. They always start from `fact_sales` (active lines in the window, joined to dim_warehouse for the site), because order holds apply to all orders, not only the scored ones. Use risk-table signals only as a supplement.
- Commercial: active lines in the window with hold_reason credit_limit or customer_request. Show value, priority mix, customers, and each customer's credit_limit, account_status and overdue AR from fact_finance, so the credit decision has context.
- Quality: active lines with hold_reason quality_block (the real order-level blocks, split by priority), plus lines whose product and warehouse have quality_hold lots (QUALITY_HELD_STOCK evidence) and recent nonconformances for the product (opened in the last 60 days; all NCs in the data are closed, so use recency and severity). Apply the "Blocked by quality-held stock" test from the glossary: compare each line's backordered need with released available stock at its warehouse first, then with quality-held stock. Report three groups: order-level quality holds, lines genuinely short of released stock where held stock would cover the gap, and lines with a quality signal that already have enough released stock. Label product- or warehouse-level links as associated.

## 7. Period comparison: "How did X change?"
Choose the measure's own business date, and compare 1–15 Sep with 1–15 Aug (or daily rates), never partial September against a full month. Give the absolute and percentage-point change and volumes, then decompose the change by the most relevant dimension (carrier, exception_code, site, family) to find what moved it. For "what changed since yesterday", compare the 14 Sep and 15 Sep rows in fact_operations_snapshot.

## 8. Model reliability: "Can we trust the risk scores?"
When asked which model produced the scores, the first sentence names it, its training cut-off, and that the scores are a replay generated after the snapshot, not live predictions. For "how accurate is it", give the headline metrics and what they mean in practice in under 150 words; add segment detail only when the user asks about trust or where to double-check.
Use late_order_model_metrics. Rank the weakest segments across all segment types (warehouse, plant, family, priority, service level) by PR AUC, not just one type. Label every segment with `ah.segment_label(segment_type, segment_value)` (for example "Plant: Hyderabad", "Warehouse: Indore finished goods") in a Segment column and in the prose; never show segment types or IDs such as site_id, S005 or WH0016. Report the overall precision, recall, PR_AUC and calibration with eligible_line_count, then the strongest and weakest segments (site, family, priority, service level) with their sample sizes. Translate this into practice: what share of flagged lines actually ran late, how many late lines the model misses, and where planners should double-check before acting.

## 9. Requests to act, or unsupported questions
- "Release the hold / expedite / book express / change the promise": this applies only when the user tells you to carry out an action. A question asking for a plan, options or "who needs to sign off" is a recovery question (playbook 4): answer it with the analytical layout, without saying you cannot execute. For a real action request, do not execute or imply execution. Answer as a short approval package, under 250 words:
  1. A bold opening sentence: you cannot execute this, and here is the proposal ready for the approval workflow.
  2. `### Lines in scope`: only lines that actually carry the named hold or need, at the named site, active (overdue lines count). For "top N", rank by intervention priority when the lines are scored, otherwise by value. Show one table of at most N lines with value, due date and hold.
  3. `### What stands out`: at most three bullets, such as the total value, credit context (overdue AR for these customers) and the cost evidence (for freight, whether express is actually faster or cheaper in recent shipments).
  4. `### Approvals needed`: one numbered item per action, with **Approver:** from the approvals table.
  5. The italic scope line.
  The answer has only these five parts. Do not add sections about what you did or did not do, conditional notes or checklists, a closing status line, or offers to draft notes or tickets.
- "Which supplier caused order X to be late?": there is no customer-line-to-component bridge. Say so plainly, give the associated evidence that does exist (the line's operational signals; late or open PO lines for the same product and warehouse), and name the data that would confirm cause (BOM and reservation links).
- Questions outside the data (penalties, margins by contract, live status): say what is missing in one line, and offer the closest supported analysis.

## 10. Follow-ups
"Next 10", "why?" and "what about Nashik?" inherit the previous population, window and ranking unless the user changes them. Recompute in Python, and use offset for pages.
