# Manufacturing Order, Sales & Inventory Workflow Dataset

## Purpose

This package is a large, linked, synthetic operational dataset for a manufacturing company implementing an end-to-end Microsoft analytics and execution solution. It connects **customer demand → sales order → availability/allocation → procurement → goods receipt → material reservation → production → quality → warehouse inventory → shipment → invoice → cash receipt → returns and corrective action**.

It is deliberately larger and more variable than a simple demo dataset: **60,000 customers**, **3,200 products**, **140,000 sales orders**, **55,000 purchase orders**, **95,000 production orders**, longitudinal order-status history, inventory lots and transactions, quality events, maintenance, cash, and daily operational snapshots.

This is **synthetic data**, not an actual manufacturer extract. It is intended for engineering, architecture, model-development, and demonstration workloads.

## End-to-end process coverage

| Capability | Main tables | Example questions |
|---|---|---|
| Demand and order intake | `demand_forecast.csv`, `sales_orders.csv`, `sales_order_lines.csv` | Which customer commitments are at risk? Where is demand above forecast? |
| Order promising and backlog | `sales_order_lines.csv`, `sales_order_status_history.csv`, `material_reservations.csv` | Which lines are backordered due to inventory, production, or credit? |
| Procure-to-pay | `purchase_orders.csv`, `purchase_order_lines.csv`, `goods_receipts.csv`, `supplier_monthly_scorecard.csv` | Which suppliers create late or poor-quality material risk? |
| Production planning and execution | `production_orders.csv`, `production_operations.csv`, `work_centers.csv` | Which plants or work centers are missing plan, running overtime, or constrained? |
| Material availability | `inventory_lots.csv`, `inventory_transactions.csv`, `material_reservations.csv` | What is available-to-promise after reservations, quality holds, and expiry? |
| Quality and containment | `quality_inspections.csv`, `nonconformances.csv`, `goods_receipts.csv` | Which lots or suppliers drive defects, scrap, rework, and cost of quality? |
| Warehouse and logistics | `shipments.csv`, `shipment_lines.csv`, `inventory_transactions.csv` | What is the OTIF gap and which carriers or warehouses cause it? |
| Revenue and cash | `invoices.csv`, `invoice_lines.csv`, `cash_receipts.csv` | Which customers have overdue AR and what is the working-capital exposure? |
| Returns and corrective actions | `customer_returns.csv`, `return_lines.csv`, `nonconformances.csv` | Which product families have returns and what is the credit/scrap impact? |
| Asset reliability | `maintenance_work_orders.csv`, `production_operations.csv` | Which equipment failures reduce capacity and cause production delay? |
| Control tower | `daily_operations_snapshots.csv` | How do service, inventory, production, quality, and cash trade off each other? |

## Microsoft implementation pattern

1. Land CSVs in **Microsoft Fabric OneLake/Lakehouse** and convert event tables to Delta/Parquet. Partition by `order_date`, `transaction_timestamp`, `receipt_date`, `forecast_month`, and site/warehouse where appropriate.
2. Build a semantic model with conformed dimensions: product, customer, supplier, site, warehouse, work center, calendar, and status dimensions. Keep order, purchase, production, inventory, shipment, quality, invoice, and receipt facts at their native grain.
3. Create an order-promising service that calculates available-to-promise from on-hand, reservations, open purchase orders, production completions, quality holds, safety stock, and lead times.
4. Use Azure ML for demand forecast accuracy, late-order risk, supplier late-receipt risk, production completion risk, quality defect risk, and inventory anomaly detection. Use temporal splits to prevent leakage.
5. Use Power BI for the executive control tower and planner workbenches; Power Apps for exception approval, material substitution, order reprioritisation, and quality disposition; Power Automate for alerts and task creation.
6. Use Foundry/Teams over a governed semantic layer for questions such as “Which customer commitments are at risk because of supplier delays?” or “What is the lowest-cost recovery plan for the Pune plant?”
7. Apply row-level security, supplier/customer confidentiality controls, audit trails, and human approval before changing production priorities, releasing quality holds, or promising customer delivery dates.

## Scale

- Raw CSV volume before the final metadata/archive: approximately **0.47 GB**.
- All tables include headers and stable identifiers.
- Money is numeric INR. Quantities are numeric in the product UOM. Dates are ISO-8601.
- Values intentionally contain seasonal demand, variable lead times, shortage, partial receipts, quality holds, scrap, rework, late shipments, overdue invoices, and returns.

## Caveat

Do not treat synthetic risk flags, customer credit information, supplier scores, quality disposition, or production recommendations as real-world policy. Production use requires ERP reconciliation, legal review, privacy controls, model-risk governance, fairness assessment, and human accountability.
