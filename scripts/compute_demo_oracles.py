"""Compute expected values for evaluations/demo_questions.json from the local snapshot.

Uses only the standard library, following the definitions in knowledge/business_context.md.
Run: .venv\\Scripts\\python.exe scripts\\compute_demo_oracles.py
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GOLD = ROOT / "data/gold_snapshots/epic_soca_6rn73kkx4n/named-outputs/snapshot/csv"
RISK = ROOT / "data/bi_tables"
ACTIVE_QUEUE = {"OPEN_NOT_YET_DUE", "OVERDUE_NOT_SHIPPED"}
ACTIVE_SALES = {"open", "on_hold", "partially_shipped"}


def rows(path: Path):
    with path.open(newline="", encoding="utf-8") as handle:
        yield from csv.DictReader(handle)


def priority_key(row):
    return (
        -float(row["intervention_priority_score"]),
        -float(row["late_probability"]),
        row["promised_ship_date"],
        row["sales_order_line_id"],
    )


def risk_summary(lines):
    at_risk = [row for row in lines if row["predicted_late_flag"] == "1"]
    return {
        "lines": len(lines),
        "orders": len({row["sales_order_id"] for row in lines}),
        "at_risk_lines": len(at_risk),
        "value_due": round(sum(float(row["line_value"]) for row in lines), 2),
        "revenue_at_risk": round(sum(float(row["line_value"]) for row in at_risk), 2),
        "expected_value_at_risk": round(
            sum(float(row["expected_line_value_at_risk"]) for row in lines), 2
        ),
    }


def main() -> None:
    risk = [row for row in rows(RISK / "late_order_risk.csv") if row["operational_queue_status"] in ACTIVE_QUEUE]
    window = [row for row in risk if row["within_14_day_window"] == "True"]
    week = [row for row in window if row["promised_ship_date"] <= "2026-09-21"]
    out: dict[str, object] = {}

    out["risk_14d"] = risk_summary(window)
    at_risk_value = defaultdict(float)
    for row in window:
        if row["predicted_late_flag"] == "1":
            at_risk_value[row["site_id"]] += float(row["line_value"])
    total = sum(at_risk_value.values())
    out["risk_14d_site_share_of_revenue_at_risk"] = {
        site: round(value / total * 100, 1) for site, value in sorted(at_risk_value.items(), key=lambda item: -item[1])
    }
    out["risk_14d_top3_by_probability"] = [
        row["sales_order_line_id"]
        for row in sorted(window, key=lambda r: (-float(r["late_probability"]), -float(r["intervention_priority_score"]), r["promised_ship_date"], r["sales_order_line_id"]))[:3]
    ]
    for site in ("S001", "S002"):
        out[f"{site}_14d"] = risk_summary([row for row in window if row["site_id"] == site])
    # A shortlist ranks the at-risk (flagged late) lines by intervention priority.
    pune = sorted(
        (row for row in window if row["site_id"] == "S001" and row["predicted_late_flag"] == "1"),
        key=priority_key,
    )
    out["pune_14d_priority_ids_1_10"] = [row["sales_order_line_id"] for row in pune[:10]]
    out["pune_14d_priority_ids_11_20"] = [row["sales_order_line_id"] for row in pune[10:20]]
    out["pune_week"] = risk_summary([row for row in week if row["site_id"] == "S001"])
    strategic = defaultdict(float)
    for row in week:
        if row["predicted_late_flag"] == "1" and row["customer_service_level"] == "strategic":
            strategic[row["customer_name"]] += float(row["line_value"])
    out["strategic_week_top_customers"] = sorted(strategic.items(), key=lambda item: -item[1])[:3]

    products = {row["product_key"]: row for row in rows(GOLD / "dim_product.csv")}
    sales_week_need = defaultdict(int)
    holds = defaultdict(lambda: [0, set(), 0.0])
    quality_block_14d = [0, 0.0]
    quality_candidates = []
    for row in rows(GOLD / "fact_sales.csv"):
        if row["order_status"] not in ACTIVE_SALES:
            continue
        key = int(row["promised_ship_date_key"])
        if 20260915 <= key <= 20260929 and row["hold_reason"] in {"credit_limit", "customer_request"}:
            bucket = holds[row["hold_reason"]]
            bucket[0] += 1
            bucket[1].add(row["sales_order_id"])
            bucket[2] += float(row["line_value"])
        if 20260915 <= key <= 20260929 and int(row["backordered_qty"]) > 0:
            quality_candidates.append(row)
        if 20260915 <= key <= 20260929 and row["hold_reason"] == "quality_block":
            quality_block_14d[0] += 1
            quality_block_14d[1] += float(row["line_value"])
        if 20260915 <= key <= 20260921 and int(row["backordered_qty"]) > 0:
            sales_week_need[(row["product_key"], row["warehouse_key"])] += int(row["backordered_qty"])
    out["commercial_holds_14d"] = {
        reason: {"lines": lines, "orders": len(orders), "value": round(value, 2)}
        for reason, (lines, orders, value) in holds.items()
    }
    out["commercial_holds_14d_total"] = {
        "lines": sum(bucket[0] for bucket in holds.values()),
        "orders": len(set().union(*(bucket[1] for bucket in holds.values()))),
        "value": round(sum(bucket[2] for bucket in holds.values()), 2),
    }
    out["quality_block_14d"] = {"lines": quality_block_14d[0], "value": round(quality_block_14d[1], 2)}
    window_ids = {row["prediction_id"]: row for row in window}
    held = {}
    for row in rows(RISK / "order_operational_evidence.csv"):
        if row["prediction_id"] in window_ids and row["evidence_code"] == "QUALITY_HELD_STOCK":
            match = re.search(r"\(([\d.]+) units blocked", row["evidence_description"])
            held[row["prediction_id"]] = float(match.group(1)) if match else 0.0
    quantities = sorted(held.values())
    out["quality_held_stock_14d"] = {
        "lines": len(held),
        "value": round(sum(float(window_ids[pid]["line_value"]) for pid in held), 2),
        "median_units_held": quantities[len(quantities) // 2] if quantities else None,
    }

    free = defaultdict(float)
    held_stock = defaultdict(float)
    for row in rows(GOLD / "fact_inventory_lots.csv"):
        key = (row["product_key"], row["warehouse_key"])
        if row["quality_status"] == "released" and int(row["expiry_date_key"] or 99999999) >= 20260915:
            free[key] += float(row["available_qty"])
        elif row["quality_status"] == "quality_hold":
            held_stock[key] += float(row["on_hand_qty"])
    # Blocked by quality-held stock: released stock short of need, held stock covers the gap.
    blocked = [0, 0.0]
    for row in quality_candidates:
        key = (row["product_key"], row["warehouse_key"])
        need = int(row["backordered_qty"])
        if free.get(key, 0.0) < need <= free.get(key, 0.0) + held_stock.get(key, 0.0):
            blocked[0] += 1
            blocked[1] += float(row["line_value"])
    out["blocked_by_quality_held_stock_14d"] = {"lines": blocked[0], "value": round(blocked[1], 2)}
    covered = partial = 0
    for (product, warehouse), need in sales_week_need.items():
        gap = need - free.get((product, warehouse), 0.0)
        if gap <= 0:
            continue
        elsewhere = sum(qty for (p, w), qty in free.items() if p == product and w != warehouse)
        covered += elsewhere >= gap
        partial += 0 < elsewhere < gap
    locally_covered = sum(free.get(key, 0.0) >= need for key, need in sales_week_need.items())
    out["transfer_week"] = {
        "need_groups": len(sales_week_need),
        "covered_locally": locally_covered,
        "short_locally_fully_coverable_elsewhere": covered,
        "partly": partial,
    }

    otd = {}
    carriers = defaultdict(lambda: [0, 0])
    for row in rows(GOLD / "fact_shipments.csv"):
        key = int(row["actual_ship_date_key"] or 0)
        period = "aug_1_15" if 20260801 <= key <= 20260815 else "sep_1_15" if 20260901 <= key <= 20260915 else None
        if period:
            stats = otd.setdefault(period, [0, 0])
            stats[0] += 1
            stats[1] += row["otd_flag"] == "Y"
            carriers[(period, row["carrier"])][0] += 1
            carriers[(period, row["carrier"])][1] += row["otd_flag"] == "Y"
    out["otd"] = {period: {"lines": n, "otd_pct": round(y / n * 100, 1)} for period, (n, y) in otd.items()}
    out["otd_by_carrier"] = {f"{p}:{c}": round(y / n * 100, 1) for (p, c), (n, y) in sorted(carriers.items())}

    metrics = list(rows(RISK / "late_order_model_metrics.csv"))
    overall = next(row for row in metrics if row["segment_type"] == "overall")
    out["model_overall"] = {k: overall[k] for k in ("eligible_line_count", "precision", "recall", "PR_AUC", "calibration_error")}
    segments = sorted((row for row in metrics if row["segment_type"] != "overall"), key=lambda r: float(r["PR_AUC"]))
    out["model_weakest_segments"] = [(r["segment_type"], r["segment_value"], r["PR_AUC"], r["eligible_line_count"]) for r in segments[:3]]

    # Week on week by site: daily averages for 8-15 Sep minus 1-7 Sep (backorders: change in lines).
    weekly = defaultdict(lambda: {"w1": [], "w2": []})
    measures = ("otif_pct", "production_attainment_pct", "on_time_ship_pct", "backorder_lines")
    for row in rows(GOLD / "fact_operations_snapshot.csv"):
        key = int(row["snapshot_date_key"])
        period = "w1" if 20260901 <= key <= 20260907 else "w2" if 20260908 <= key <= 20260915 else None
        if period:
            for measure in measures:
                weekly[(row["site_id"], measure)][period].append(float(row[measure]))
    out["plants_week_on_week_change"] = {
        measure: dict(sorted(
            (
                (site, round(sum(v["w2"]) / len(v["w2"]) - sum(v["w1"]) / len(v["w1"]), 2))
                for (site, m), v in weekly.items() if m == measure
            ),
            key=lambda item: item[1],
        ))
        for measure in measures
    }

    # Purchase orders buy only raw material and packaging, so none link directly to a
    # finished-good order line; supplier evidence can only be associated by site.
    warehouse_site = {row["warehouse_key"]: row["site_id"] for row in rows(GOLD / "dim_warehouse.csv")}
    product_types = Counter(products[row["product_key"]]["product_type"] for row in rows(GOLD / "fact_procurement.csv"))
    late_open = Counter()
    for row in rows(GOLD / "fact_procurement.csv"):
        promised = int(row["promised_receipt_date_key"] or 0)
        if row["po_status"] not in {"received", "closed", "cancelled"} and 0 < promised < 20260915:
            late_open[warehouse_site.get(row["warehouse_key"])] += 1
    out["procurement_product_types"] = dict(product_types)
    out["late_open_po_lines_by_site"] = dict(late_open.most_common())

    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
