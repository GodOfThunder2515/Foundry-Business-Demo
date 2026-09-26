## Dataset overview (answer questions about the data from here, without code)

The agent has **17 business tables** loaded, all CSV:
- **13 Gold tables** from the Fabric Gold snapshot `epic_soca_6rn73kkx4n`:
  - 9 facts: fact_sales, fact_shipments, fact_inventory_lots, fact_material_reservations, fact_procurement, fact_quality_inspections, fact_quality_nonconformances, fact_finance, fact_operations_snapshot.
  - 4 dimensions: dim_customer, dim_product, dim_supplier, dim_warehouse.
- **4 late-order-risk tables** from the Azure ML model package: late_order_risk, late_order_risk_factors, order_operational_evidence, late_order_model_metrics.

The full Gold snapshot has 16 tables. Three are deliberately not loaded: dim_date (dates are parsed from keys instead), dim_region (no link to any fact) and fact_inventory_transactions (production movement history, not needed for commitment analysis). If a question needs them, say they are not loaded for this agent.

Two further uploaded files are support files, not data, and are never counted as tables: `dataset_catalog.json` (the machine-readable schema) and `analysis_helper.py` (display and lookup utilities). Coverage: history since 2024; default analysis window June–September 2026; as of 2026-09-15 (synthetic demonstration data). The model is a logistic regression (v1), trained to 2026-08-31, with replay scores for lines ordered 1–15 Sep 2026.

Answer questions about the dataset (which tables exist, what a table or field means, coverage, as-of date, model identity) from this section and the ones below. Use code only when the question needs values from the data, such as row counts or quality metrics.

## Files and `dataset_catalog.json`

Files are mounted as `/mnt/data/assistant-<fileid>-<filename>`; always resolve them with `path("<filename>")` from the setup. Never show file paths, file IDs or mounted names to the user; refer to tables by name (for example "the shipments table").

`dataset_catalog.json` has exactly three top-level keys. Tables are nested one level down in two groups, so never count the top-level keys:
- `snapshot`: id, data_as_of, historical_start, commitment_end.
- `tables`: the 16 Gold tables (13 loaded), keyed by table name. Each entry has filename, grain, primary_key, evidence_class, columns (column → type), joins (list of {table, left, right, cardinality}), date_fields (column → meaning) and aggregation_warnings.
- `risk_tables`: the 4 risk tables, with the same fields, except that usage_rules replaces aggregation_warnings.

The catalog documents all 16 Gold tables, including the 3 not loaded. Read it with the helper, which merges both groups, keeps only the 17 loaded tables, and labels each entry `group` = "gold" or "risk":

```python
import json
catalog = json.load(open(path("dataset_catalog.json")))
tables = ah.catalog_tables(catalog)   # 17 entries: {name: entry}
tables["fact_shipments"]["joins"]     # print only the entry or field you need
```

Use it for what this section summarises but does not spell out: exact column types, join keys and cardinality (to avoid duplicating value in one-to-many joins), date-field meanings, and the risk tables' usage rules. Never print the whole catalog.

Date formats: Gold tables use integer `*_date_key` values (`yyyyMMdd`); risk tables use ISO date strings. All money is INR.

## Late-order risk package — start here for any "at risk" question

`late_order_risk.csv` — one replay prediction per scored sales-order line (5,362 rows). Scope: lines **ordered 2026-09-01 to 2026-09-15** in the five finished-good families (engine_systems, vehicle_electronics, industrial_pumps, consumer_appliances, fabricated_frames). It is not the full order book.
- Columns: prediction_id, sales_order_line_id, sales_order_id, order_number, line_number, customer_id, customer_name, product_id, product_name, product_family, site_id, warehouse_id, prediction_timestamp, late_probability, late_probability_percentile, predicted_late_flag, decision_threshold, model_name, model_version, training_data_cutoff, feature_contract_version, explanation_baseline_probability, priority_as_of_date, late_probability_score, line_value_score, customer_service_score, promise_urgency_score, intervention_priority_score, intervention_priority_percentile, intervention_priority_band, priority_formula_version, ordered_qty, line_value, expected_line_value_at_risk, customer_service_level, source_order_priority, order_date, requested_ship_date, promised_ship_date, days_to_promise, within_14_day_window, operational_queue_status, first_actual_ship_date, shipment_delay_days, days_late, outcome_status, outcome_known_at, final_late_flag, prediction_result, evaluation_eligible, evaluation_exclusion_reason, data_quality_warning
- Values: operational_queue_status ∈ {OPEN_NOT_YET_DUE, OVERDUE_NOT_SHIPPED, SHIPPED_BY_SNAPSHOT, CANCELLED}; intervention_priority_band ∈ {Critical, High, Medium, Low, NOT_ACTIVE}; customer_service_level ∈ {strategic, priority, standard}; source_order_priority ∈ {allocation_critical, urgent, priority, standard}; site_id S001–S008; warehouse_id WH0001–WH0016 (string). Customer and product names are already denormalized here.
- Use: late_probability (0–1) = chance of late first shipment. intervention_priority_score (0–100) = where to act first (risk × value × service level × urgency); it is not a probability. expected_line_value_at_risk = late_probability × line_value.
- Never use in an as-of answer (hindsight): first_actual_ship_date, shipment_delay_days, days_late, outcome_status, outcome_known_at, final_late_flag, prediction_result, evaluation_*.

`late_order_risk_factors.csv` — ranked model drivers per prediction (about 8 per line). Columns: prediction_id, sales_order_line_id, factor_rank, factor_name, factor_display_name, factor_value, contribution_direction (INCREASES_RISK / DECREASES_RISK), contribution_percentage_points, explanation_method, model_version. Use factor_display_name for users. Most common drivers: promise extension vs. request, customer's prior order lines, ordered quantity, warehouse/site historical late rate, order priority. To find what drives risk across a group, count or sum INCREASES_RISK contributions by factor_display_name. These explain the model score, not operational cause.

`order_operational_evidence.csv` — rule-derived operational signals per scored line, as of 2026-09-15 (6,900 rows; a line can have several or none). Columns: prediction_id, sales_order_line_id, evidence_code, evidence_description, evidence_value, severity (HIGH/MEDIUM), matching_basis, confidence (HIGH/MEDIUM/LOW), source_table, source_record_id, evidence_as_of_date, rule_version.
- evidence_code → recovery path: LOGISTICS_EXCEPTION (linked shipment exception production_delay or carrier_capacity → production or logistics), QUALITY_HELD_STOCK (a lot for the product/warehouse is on quality hold → quality), PRODUCT_SITE_CAPACITY_PRESSURE (site production attainment below plan → production), LOW_ALLOCATION_RATIO (little or no stock allocated to the line → inventory), COMMERCIAL_HOLD (order hold: credit_limit, material_shortage, quality_block, customer_request → commercial), POSSIBLE_INVENTORY_SHORTAGE (available stock below need → inventory).
- Read evidence_description for magnitude, and do not treat every signal as material. A QUALITY_HELD_STOCK signal only shows that held lots exist for the product and warehouse; test whether they actually block the line (see business concepts).

`late_order_model_metrics.csv` — model quality for 2026-09-01 to 2026-09-15 (37 rows). Columns: model_name, model_version, evaluation_period, segment_type (overall, site_id, warehouse_id, product_family, order_priority, service_level), segment_value, eligible_line_count, late_line_count, late_rate, recall, precision, false_positive_count, false_negative_count, PR_AUC, ROC_AUC, Brier_score, calibration_error, decision_threshold, top_5_pct_late_capture, top_10_pct_late_capture, top_20_pct_late_capture. Always quote eligible_line_count with a metric.

## Core Gold facts

`fact_sales.csv` — one row per sales-order line (367,715 rows, all history since 2024). Key sales_order_line_id.
- Columns: sales_order_line_id, sales_order_id, customer_key, product_key, warehouse_key, order_date_key, requested_ship_date_key, promised_ship_date_key, requested_delivery_date_key, order_number, line_number, currency, channel, priority, order_status, line_status, hold_reason, ordered_qty, allocated_qty, shipped_qty, backordered_qty, unit_price, discount_pct, tax_pct, line_value, backorder_flag, load_timestamp
- Values: order_status ∈ {open, on_hold, partially_shipped, shipped, closed, cancelled}; priority ∈ {allocation_critical, urgent, priority, standard}; hold_reason ∈ {credit_limit, material_shortage, quality_block, customer_request, blank}; channel ∈ {distributor_portal, edi, sales_rep, key_account_api, ecommerce}.
- Warning: line_status (99% "backordered") and backorder_flag (99% "Y") are not meaningful. Use order_status and backordered_qty > 0 instead.
- Joins: customer_key → dim_customer, product_key → dim_product, warehouse_key → dim_warehouse (for site_id and warehouse name).

`fact_shipments.csv` — one row per shipment line (283,415 rows). Joins to sales on sales_order_line_id (many-to-one; aggregate before joining).
- Columns: shipment_line_id, shipment_id, sales_order_line_id, sales_order_id, product_key, warehouse_key, customer_key, actual_ship_date_key, planned_ship_date_key, planned_delivery_date_key, actual_delivery_date_key, shipment_number, carrier, service_level, shipment_status, otd_flag, exception_code, line_status, lot_id, shipped_qty, short_ship_qty, allocated_freight_cost, load_timestamp
- Values: carrier ∈ {Delhivery, BlueDart, Safexpress, TCI, DHL, CustomerPickup}; service_level ∈ {standard, express, dedicated}; otd_flag Y/N; exception_code ∈ {production_delay, carrier_capacity, blank}; shipment_status ∈ {delivered, in_transit}.
- Warning: line_status is 99% "short_shipped" and short_ship_qty > 0 on 99% of lines, so neither identifies real short shipments. Use otd_flag for delivery performance. allocated_freight_cost is the only freight-cost evidence; express vs. standard cost per unit shipped is the basis for premium-freight cost estimates.

`fact_inventory_lots.csv` — current lot position by warehouse (250,000 rows; snapshot, no date filter). Columns: lot_id, product_key, warehouse_key, supplier_key, manufacture_date_key, expiry_date_key, quality_status (released, quality_hold, expired), on_hand_qty, available_qty, blocked_qty, unit_cost, inventory_value, manufacture_date, expiry_date, load_timestamp. Freely available stock = available_qty on released lots with expiry_date_key ≥ 20260915.

## Supporting Gold facts

`fact_procurement.csv` — purchase-order line (131,746 rows). Columns: purchase_order_line_id, purchase_order_id, po_number, supplier_key, product_key, warehouse_key, order_date_key, expected_receipt_date_key, promised_receipt_date_key, actual_receipt_date_key, po_status (open, partially_received, closed, cancelled), currency, buyer_id, late_risk_flag (Y/N), line_number, line_status, ordered_qty, received_qty, accepted_qty, rejected_qty, quality_hold_qty, pending_qty, unit_cost, line_value, accepted_value, rejected_value, receipt_pct, load_timestamp. Use for supplier and inbound-material signals; there is no bridge to a customer line.

`fact_material_reservations.csv` — production material reservation (607,100 rows). Columns: reservation_id, production_order_id, product_key, warehouse_key, required_date_key, reservation_status (short, reserved, issued), required_qty, reserved_qty, issued_qty, short_qty, reservation_fill_pct, required_date, load_timestamp. 94% of rows are "short", so compare shortage rates between groups rather than citing the raw share.

`fact_quality_inspections.csv` — final-product inspection (87,493 rows). Columns: inspection_id, product_key, inspection_date_key, inspection_type, reference_type, reference_id, inspector_id, product_id, lot_id, inspection_result (pass/fail), hold_flag (Y/N), sample_qty, passed_qty, failed_qty, defect_rate_pct, inspection_date, load_timestamp.

`fact_quality_nonconformances.csv` — quality nonconformance (6,528 rows). Columns: nc_id, product_key, opened_date_key, closure_date_key, nc_number, reference_type, reference_id, product_id, lot_id, nc_category (functional, dimensional, surface_finish, electrical, packaging), severity (minor, major, critical), root_cause_category (machine_setting, process_variation, operator_error, supplier_material, design_tolerance), disposition (rework, scrap, use_as_is, return_to_supplier), quantity_affected, cost_of_quality, opened_date, closure_date, load_timestamp. Every NC in this snapshot is closed, so use opened_date_key for recency.

`fact_finance.csv` — invoice with receipt state (123,405 rows). Columns: invoice_id, invoice_number, sales_order_id, customer_key, invoice_date_key, due_date_key, receipt_date_key, invoice_status (paid, partially_paid, open), subtotal, tax_amount, freight_amount, invoice_total, outstanding_amount, invoice_line_count, total_invoiced_qty, total_discount_amount, line_tax_amount, line_total_amount, cash_receipt_id, payment_channel, bank_reference_hash, receipt_status, receipt_amount, calculated_outstanding_amount, invoice_date, due_date, receipt_date, invoice_load_timestamp. Joins to sales at order level (sales_order_id), never at line level.

`fact_operations_snapshot.csv` — daily KPIs by site and warehouse for 2026-09-01 to 2026-09-30 (240 rows). Columns: site_id, warehouse_key, snapshot_date_key, open_sales_orders, orders_due_7d, backorder_lines, production_plan_qty, production_completed_qty, supplier_late_po_count, quality_hold_qty, sales_order_value_open, inventory_value, inventory_accuracy_pct, production_attainment_pct, scrap_rate_pct, on_time_ship_pct, otif_pct, ar_overdue_amount, snapshot_date, data_refresh_timestamp, load_timestamp. Use rows with snapshot_date_key ≤ 20260915 only; later rows are beyond the as-of date.

## Dimensions

`dim_warehouse.csv` (16 rows): warehouse_key, warehouse_id, storage_capacity_cbm, site_id, warehouse_code, warehouse_name, warehouse_type (raw_material, finished_goods), temperature_controlled_flag, active_flag, load_timestamp. Site map: S001 Pune (WH0001 raw, WH0002 FG), S002 Nashik (WH0003, WH0004), S003 Ahmedabad (WH0005, WH0006), S004 Bengaluru (WH0007, WH0008), S005 Hyderabad (WH0009, WH0010), S006 Delhi (WH0011, WH0012), S007 Kolkata (WH0013, WH0014), S008 Indore (WH0015, WH0016). warehouse_key n = WH000n.

`dim_customer.csv` (60,000 rows): customer_key, customer_id, customer_code, customer_name, customer_type (distributor, industrial, retail_chain, oem, export_customer), industry, city, state, country, service_level (strategic, priority, standard), payment_terms_days, credit_limit, account_status (active, on_hold, inactive), created_date.

`dim_product.csv` (3,200 rows): product_key, product_id, lead_time_days, standard_cost, sku, safety_stock_units, list_price, product_name, reorder_point_units, product_type (finished_good, semi_finished, raw_material, packaging), lot_size_units, product_family, uom, make_buy_flag (make, buy), active_flag, load_timestamp. Finished-good families: engine_systems, vehicle_electronics, industrial_pumps, consumer_appliances, fabricated_frames.

`dim_supplier.csv` (3,500 rows): supplier_key, supplier_id, supplier_code, supplier_name, supplier_type (strategic, approved, contract_manufacturer, spot), city, state, country, payment_terms_days, on_time_baseline_pct, quality_baseline_pct, risk_tier (A, B, C), active_flag.

