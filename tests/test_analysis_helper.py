import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from src.analysis_helper import (
    SIGNAL_LABELS,
    SITE_NAMES,
    build_analysis_result,
    catalog_tables,
    find_uploaded_file,
    format_table,
    main_signal_by_line,
    parse_yyyymmdd,
    segment_label,
    show_table,
)


class FindUploadedFileTests(unittest.TestCase):
    def test_prefers_exact_filename(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            exact = root / "fact_sales.csv"
            exact.touch()
            (root / "file-123-fact_sales.csv").touch()

            self.assertEqual(find_uploaded_file("fact_sales.csv", root), exact)

    def test_resolves_foundry_prefixed_filename(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mounted = root / "file-123-fact_sales.csv"
            mounted.touch()

            self.assertEqual(find_uploaded_file("fact_sales.csv", root), mounted)

    def test_missing_filename_fails_clearly(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(FileNotFoundError, "fact_sales.csv"):
                find_uploaded_file("fact_sales.csv", Path(directory))

    def test_ambiguous_prefixed_filename_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "file-1-fact_sales.csv").touch()
            (root / "file-2-fact_sales.csv").touch()

            with self.assertRaisesRegex(ValueError, "Multiple uploaded files"):
                find_uploaded_file("fact_sales.csv", root)


class ParseDateTests(unittest.TestCase):
    def test_future_date_key_is_not_lost(self):
        self.assertEqual(parse_yyyymmdd(20260930), date(2026, 9, 30))

    def test_blank_and_null_dates_are_null(self):
        self.assertIsNone(parse_yyyymmdd(None))
        self.assertIsNone(parse_yyyymmdd(""))

    def test_invalid_date_fails(self):
        with self.assertRaisesRegex(ValueError, "yyyyMMdd"):
            parse_yyyymmdd("2026-09-30")


class AnalysisResultTests(unittest.TestCase):
    def records(self, count: int) -> list[dict[str, object]]:
        return [
            {
                "id": f"L{index:02d}",
                "score": Decimal("0.90") if index < 2 else Decimal(index) / 100,
                "date": date(2026, 9, 15),
                "extra": index,
            }
            for index in range(count)
        ]

    def test_grouped_results_are_sorted_and_capped_at_15(self):
        result = build_analysis_result(
            matched_rows=40,
            filters=["status=open"],
            data_as_of="2026-09-15",
            summary_metrics={"value": Decimal("12.30")},
            records=self.records(20),
            sort_spec=[("score", "desc"), ("id", "asc")],
            columns=["id", "score", "date"],
        )

        self.assertEqual(len(result["top_results"]), 15)
        self.assertEqual(result["top_results"][0]["id"], "L00")
        self.assertEqual(result["top_results"][1]["id"], "L01")
        self.assertEqual(result["summary_metrics"]["value"], "12.30")
        self.assertEqual(result["top_results"][0]["date"], "2026-09-15")
        self.assertTrue(result["truncated"])

    def test_detail_results_use_10_row_pages(self):
        result = build_analysis_result(
            matched_rows=25,
            filters=[],
            data_as_of="2026-09-15",
            summary_metrics={},
            records=self.records(25),
            sort_spec=[("id", "asc")],
            detail=True,
            offset=10,
            columns=["id"],
        )

        self.assertEqual([row["id"] for row in result["top_results"]], [f"L{i:02d}" for i in range(10, 20)])
        self.assertTrue(result["truncated"])

    def test_empty_result_preserves_scope(self):
        result = build_analysis_result(
            matched_rows=0,
            filters=["warehouse=Pune"],
            data_as_of="2026-09-15",
            summary_metrics={},
            records=[],
            sort_spec=[],
        )

        self.assertEqual(result["population"]["matched_rows"], 0)
        self.assertEqual(result["population"]["filters"], ["warehouse=Pune"])
        self.assertEqual(result["population"]["data_as_of"], "2026-09-15")
        self.assertFalse(result["truncated"])

    def test_columns_are_limited_to_12(self):
        records = [{f"c{i}": i for i in range(13)}]
        result = build_analysis_result(
            matched_rows=1,
            filters=[],
            data_as_of="2026-09-15",
            summary_metrics={},
            records=records,
            sort_spec=[],
        )

        self.assertEqual(len(result["top_results"][0]), 12)

    def test_nested_values_are_json_safe(self):
        result = build_analysis_result(
            matched_rows=1,
            filters=[],
            data_as_of="2026-09-15",
            summary_metrics={"nested": {"amount": Decimal("1.20"), "at": datetime(2026, 9, 15, 10, 30)}},
            records=[{"id": "L1"}],
            sort_spec=[("id", "asc")],
        )

        json.dumps(result)
        self.assertEqual(result["summary_metrics"]["nested"]["amount"], "1.20")
        self.assertEqual(result["summary_metrics"]["nested"]["at"], "2026-09-15T10:30:00")

    def test_invalid_arguments_fail(self):
        base = {
            "matched_rows": 1,
            "filters": [],
            "data_as_of": "2026-09-15",
            "summary_metrics": {},
            "records": [{"id": "L1"}],
        }
        with self.assertRaises(ValueError):
            build_analysis_result(**base, sort_spec=[("id", "sideways")])
        with self.assertRaises(KeyError):
            build_analysis_result(**base, sort_spec=[("missing", "asc")])
        with self.assertRaises(ValueError):
            build_analysis_result(**{**base, "matched_rows": -1}, sort_spec=[])
        with self.assertRaises(ValueError):
            build_analysis_result(**base, sort_spec=[], offset=-1)


class FakeFrame:
    """Minimal stand-in for a pandas DataFrame, which is unavailable locally."""

    def __init__(self, rows: list[dict[str, object]]):
        self.rows = rows

    def to_dict(self, orient: str):
        assert orient == "records"
        return list(self.rows)


class FormatTableTests(unittest.TestCase):
    def rows(self, count: int) -> list[dict[str, object]]:
        return [
            {
                "sales_order_line_id": f"SOL{index:03d}",
                "late_probability": 0.8354,
                "expected_line_value_at_risk": 12735.23,
                "promised_ship_date": "2026-09-18",
            }
            for index in range(count)
        ]

    def test_renders_markdown_with_business_labels_and_formats(self):
        text = format_table(
            self.rows(1),
            ["sales_order_line_id", "late_probability", "expected_line_value_at_risk", "promised_ship_date"],
            labels={
                "sales_order_line_id": "Order line",
                "late_probability": "Late risk",
                "expected_line_value_at_risk": "Value at risk",
                "promised_ship_date": "Due",
            },
            formats={
                "late_probability": "pct",
                "expected_line_value_at_risk": "inr",
                "promised_ship_date": "date",
            },
        )

        lines = text.splitlines()
        self.assertEqual(lines[0], "| Order line | Late risk | Value at risk | Due |")
        self.assertEqual(lines[1], "|---|---|---|---|")
        self.assertEqual(lines[2], "| SOL000 | 83.5% | ₹12.7K | 18 Sep |")
        self.assertIn("Rows 1–1 of 1", text)

    def test_value_formats(self):
        rows = [
            {"inr": 950.4, "big": 4053939.78, "ratio": 0.5, "points": 77.94, "qty": 47488, "key": 20260915, "old": "2025-03-26 00:00:00"},
        ]
        text = format_table(
            rows,
            ["inr", "big", "ratio", "points", "qty", "key", "old"],
            formats={"inr": "inr", "big": "inr", "ratio": "pct", "points": "pct100", "qty": "int", "key": "date", "old": "date"},
        )

        self.assertIn("| ₹950 | ₹4.05M | 50.0% | 77.9% | 47,488 | 15 Sep | 26 Mar 2025 |", text)

    def test_segment_label_uses_business_names(self):
        self.assertEqual(segment_label("site_id", "S005"), "Plant: Hyderabad")
        self.assertEqual(segment_label("warehouse_id", "WH0016"), "Warehouse: Indore finished goods")
        self.assertEqual(segment_label("warehouse_id", "WH0009"), "Warehouse: Hyderabad raw material")
        self.assertEqual(segment_label("product_family", "vehicle_electronics"), "Family: Vehicle electronics")
        self.assertEqual(segment_label("order_priority", "allocation_critical"), "Priority: Allocation critical")
        self.assertEqual(segment_label("service_level", "strategic"), "Service level: Strategic")
        self.assertEqual(segment_label("overall", "all"), "All scored lines")

    def test_codes_embedded_in_text_cells_lose_underscores(self):
        text = format_table([{"segment": "warehouse_id: WH0010"}], ["segment"])

        self.assertIn("| warehouse id: WH0010 |", text)

    def test_code_like_text_cells_become_plain_words(self):
        rows = [{"hold": "credit_limit", "signal": "QUALITY_HELD_STOCK", "customer": "Farhan Jadhav", "line": "SOL000249384"}]

        text = format_table(rows, ["hold", "signal", "customer", "line"])

        self.assertIn("| Credit limit | Quality held stock | Farhan Jadhav | SOL000249384 |", text)

    def test_unformatted_numbers_get_separators(self):
        class NumpyLikeInt:
            def item(self):
                return 47488

        text = format_table([{"n": NumpyLikeInt(), "d": Decimal("1234.5"), "i": 1406}], ["n", "d", "i"])

        self.assertIn("| 47,488 | 1,234.50 | 1,406 |", text)

    def test_missing_values_and_pipes_are_safe(self):
        text = format_table([{"a": None, "b": float("nan"), "c": "x|y"}], ["a", "b", "c"])

        self.assertIn("| — | — | x/y |", text)

    def test_caps_rows_and_reports_full_population(self):
        text = format_table(self.rows(30), ["sales_order_line_id"], total=1406)

        body = [line for line in text.splitlines() if line.startswith("| SOL")]
        self.assertEqual(len(body), 10)
        self.assertIn("Rows 1–10 of 1,406", text)

    def test_limit_never_exceeds_group_cap(self):
        text = format_table(self.rows(30), ["sales_order_line_id"], limit=50)

        body = [line for line in text.splitlines() if line.startswith("| SOL")]
        self.assertEqual(len(body), 15)

    def test_offset_pages_through_rows(self):
        text = format_table(self.rows(25), ["sales_order_line_id"], offset=10)

        body = [line for line in text.splitlines() if line.startswith("| SOL")]
        self.assertEqual(body[0], "| SOL010 |")
        self.assertEqual(len(body), 10)
        self.assertIn("Rows 11–20 of 25", text)

    def test_accepts_dataframe_like_objects(self):
        text = format_table(FakeFrame(self.rows(2)), ["sales_order_line_id"])

        self.assertIn("| SOL001 |", text)

    def test_rejects_too_many_or_missing_columns(self):
        with self.assertRaisesRegex(ValueError, "8"):
            format_table([{f"c{i}": i for i in range(9)}], [f"c{i}" for i in range(9)])
        with self.assertRaisesRegex(KeyError, "missing"):
            format_table([{"a": 1}], ["a", "missing"])
        with self.assertRaisesRegex(ValueError, "format"):
            format_table([{"a": 1}], ["a"], formats={"a": "dollars"})

    def test_show_table_prints_markdown(self):
        output = io.StringIO()
        with redirect_stdout(output):
            result = show_table([{"a": 1}], ["a"])

        self.assertIsNone(result)
        self.assertIn("| a |", output.getvalue())


class BusinessLabelTests(unittest.TestCase):
    def test_site_names_cover_all_eight_sites(self):
        self.assertEqual(SITE_NAMES["S001"], "Pune")
        self.assertEqual(SITE_NAMES["S004"], "Bengaluru")
        self.assertEqual(len(SITE_NAMES), 8)

    def test_signal_labels_cover_every_evidence_code(self):
        self.assertEqual(
            set(SIGNAL_LABELS),
            {
                "LOGISTICS_EXCEPTION",
                "QUALITY_HELD_STOCK",
                "PRODUCT_SITE_CAPACITY_PRESSURE",
                "LOW_ALLOCATION_RATIO",
                "COMMERCIAL_HOLD",
                "POSSIBLE_INVENTORY_SHORTAGE",
            },
        )

    def test_main_signal_picks_highest_severity_then_confidence(self):
        evidence = [
            {"sales_order_line_id": "L1", "evidence_code": "LOGISTICS_EXCEPTION", "severity": "MEDIUM", "confidence": "HIGH"},
            {"sales_order_line_id": "L1", "evidence_code": "COMMERCIAL_HOLD", "severity": "HIGH", "confidence": "HIGH"},
            {"sales_order_line_id": "L2", "evidence_code": "QUALITY_HELD_STOCK", "severity": "MEDIUM", "confidence": "LOW"},
            {"sales_order_line_id": "L2", "evidence_code": "LOGISTICS_EXCEPTION", "severity": "MEDIUM", "confidence": "HIGH"},
        ]

        self.assertEqual(
            main_signal_by_line(evidence),
            {"L1": "Commercial hold", "L2": "Logistics exception"},
        )

    def test_main_signal_accepts_dataframe_like_input(self):
        frame = FakeFrame([
            {"sales_order_line_id": "L1", "evidence_code": "LOW_ALLOCATION_RATIO", "severity": "HIGH", "confidence": "MEDIUM"},
        ])

        self.assertEqual(main_signal_by_line(frame), {"L1": "Low stock allocation"})


class CatalogTablesTests(unittest.TestCase):
    def test_merges_gold_and_risk_groups_with_group_label(self):
        catalog = {
            "snapshot": {"data_as_of": "2026-09-15"},
            "tables": {"fact_sales": {"filename": "fact_sales.csv"}},
            "risk_tables": {"late_order_risk": {"filename": "late_order_risk.csv"}},
        }

        tables = catalog_tables(catalog)

        self.assertEqual(set(tables), {"fact_sales", "late_order_risk"})
        self.assertEqual(tables["fact_sales"]["group"], "gold")
        self.assertEqual(tables["late_order_risk"]["group"], "risk")
        self.assertNotIn("group", catalog["tables"]["fact_sales"])

    def test_repository_catalog_lists_the_seventeen_loaded_tables(self):
        catalog = json.loads(
            (Path(__file__).resolve().parents[1] / "knowledge/dataset_catalog.json").read_text(encoding="utf-8")
        )

        tables = catalog_tables(catalog)

        self.assertEqual(len(tables), 17)
        self.assertEqual(sum(t["group"] == "risk" for t in tables.values()), 4)
        self.assertFalse(set(tables) & {"dim_date", "dim_region", "fact_inventory_transactions"})


class DataPathTests(unittest.TestCase):
    def test_find_uploaded_file_defaults_to_code_interpreter_mount(self):
        with self.assertRaisesRegex(FileNotFoundError, "no_such_table.csv"):
            find_uploaded_file("no_such_table.csv")


if __name__ == "__main__":
    unittest.main()
