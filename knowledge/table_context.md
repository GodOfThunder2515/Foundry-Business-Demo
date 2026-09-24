`fact_sales` — Sales-order-line grain; key `sales_order_line_id`. Joins to customer, product, and warehouse dimensions. Start commitment analysis here; future promise keys extend beyond `dim_date`.

`fact_shipments` — Shipment-line grain; key `shipment_line_id`. Joins to sales by `sales_order_line_id`. Aggregate shipments before joining to sales values.

`fact_inventory_lots` — Current lot/warehouse inventory grain; key `lot_id`. Use available, blocked, quality, and expiry fields for recovery; this is current state, not movement history.

`fact_inventory_transactions` — Inventory-movement grain; key `inventory_transaction_id`. Use for movement history and reasons, not current stock.

`fact_material_reservations` — Production material-reservation grain; key `reservation_id`. No supplied bridge confirms a reservation as the cause of a customer line.

`fact_procurement` — Purchase-order-line grain; key `purchase_order_line_id`. Joins to supplier, product, and warehouse; no BOM/customer-line bridge is supplied.

`fact_quality_inspections` — Inspection grain; key `inspection_id`. Product, lot, reference, result, defect, and hold evidence; production references do not bridge to sales lines.

`fact_quality_nonconformances` — Nonconformance grain; key `nc_id`. Contains recorded NC cause and disposition; that cause is not automatically a customer-line cause.

`fact_finance` — Invoice/receipt-state grain; key `invoice_id`. Aggregate to order before comparing with sales lines to avoid duplicating invoice or order value.

`fact_operations_snapshot` — Site/warehouse/day KPI grain; composite key `site_id`, `warehouse_key`, `snapshot_date_key`. Only about 30 days of history is available.

`dim_customer` — Customer grain; key `customer_key`. Identity, service level, payment terms, credit limit, and account status.

`dim_product` — Product grain; key `product_key`. Family, cost, price, lead time, stock policy, UOM, and make/buy attributes.

`dim_supplier` — Supplier grain; key `supplier_key`. Identity, location, delivery/quality baselines, risk tier, and status.

`dim_warehouse` — Warehouse grain; key `warehouse_key`. Site, type, capacity, controls, and status; join through the surrogate key.

`dim_date` — Calendar-date grain; key `date_key`. Ends on 2026-09-15, so parse later fact keys directly as `yyyyMMdd`.

`dim_region` — Region grain; key `region_key`. No documented relationship to facts; do not use for quantitative attribution.

`late_order_risk` — One replay score per sales-order line. Use `late_probability` for likelihood of late first shipment and `intervention_priority_score`/band for action prioritization. Active queue statuses are `OPEN_NOT_YET_DUE` and `OVERDUE_NOT_SHIPPED`. The business snapshot is 2026-09-15; generation timestamp 2026-09-23 identifies a replay, not a live score.

`late_order_risk_factors` — Ranked model-explanation rows per prediction. Factor contributions explain the model score; they do not prove operational causation. Select or aggregate factors before joining.

`order_operational_evidence` — Rule-derived as-of operational signals directly keyed to scored sales lines. Use severity, confidence, matching basis, and source reference as supporting evidence, while avoiding unsupported causal claims.

`late_order_model_metrics` — Model-evaluation rows for 2026-09-01 through 2026-09-15 at overall and segment grain. Use these to qualify reliability, always with sample size; never use them as individual-line predictions.
