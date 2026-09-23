import json
import tempfile
import unittest
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from src.analysis_helper import (
    build_analysis_result,
    find_uploaded_file,
    parse_yyyymmdd,
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


if __name__ == "__main__":
    unittest.main()
