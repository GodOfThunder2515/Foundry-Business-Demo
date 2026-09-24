## 1. Risk ranking

For “Which commitments are most at risk?”, filter `late_order_risk` to the requested promise window and active queue statuses, then rank by `late_probability` with deterministic business tie-breakers. Explain model factors separately from operational evidence, disclose `logistic_regression:v1`, the 2026-08-31 training cutoff, the 2026-09-15 snapshot, and the 2026-09-23 replay-generation timestamp. Return the full population and no more than 10 lines in the final answer.

## 2. Period comparison

For “Is performance deteriorating?”, select the measure and business date, compute complete June–August periods, label September partial through 2026-09-15, and explain both absolute and percentage changes. Do not compare a partial month as though it were complete.

## 3. Cause investigation

For “Why are Pune commitments at risk?”, establish affected sales lines first, then examine directly linked shipment facts and associated product/warehouse/time signals from inventory, reservations, procurement, operations, and quality. Label unsupported upstream attribution as association rather than confirmed cause.

## 4. Recovery comparison

For “What recovery action is worth taking?”, quantify affected commitments and usable inventory, compare supported alternatives, state benefit and incremental cost evidence, name assumptions and approver, and do not call an option lowest cost when costs are missing.

## 5. Unsupported question

For “Which supplier caused order X to be late?”, check for a documented order-line-to-component/procurement relationship. If absent, say the exact cause cannot be established, provide only relevant associated supplier/product/site evidence, and identify the missing bridge needed for confirmation.
