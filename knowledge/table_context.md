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

Optional prediction interfaces: `late_order_risk_predictions.csv` at sales-line grain, `supplier_receipt_risk_predictions.csv` at PO-line grain, `production_completion_risk_predictions.csv` at production-order grain, and `quality_risk_predictions.csv` at its declared scored-entity grain. Report prediction timestamp, model name/version, probability/band, and separate reason codes from confirmed operational causes.
