import csv
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "knowledge/dataset_catalog.json"
CSV_ROOT = ROOT / "data/gold_snapshots/epic_soca_6rn73kkx4n/named-outputs/snapshot/csv"


class DatasetCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))

    def test_catalog_covers_exactly_the_gold_csvs(self):
        actual = {path.stem for path in CSV_ROOT.glob("*.csv")}
        self.assertEqual(set(self.catalog["tables"]), actual)

    def test_catalog_columns_and_keys_exist_in_real_headers(self):
        for name, table in self.catalog["tables"].items():
            with self.subTest(table=name):
                path = CSV_ROOT / table["filename"]
                with path.open(newline="", encoding="utf-8-sig") as handle:
                    header = set(next(csv.reader(handle)))
                self.assertEqual(set(table["columns"]), header)
                self.assertLessEqual(set(table["primary_key"]), header)
                self.assertTrue(table["grain"])
                self.assertIn(table["evidence_class"], {"recorded_fact", "dimension", "snapshot"})
                self.assertIsInstance(table["date_fields"], dict)
                self.assertIsInstance(table["aggregation_warnings"], list)

    def test_every_join_references_existing_columns(self):
        tables = self.catalog["tables"]
        for name, table in tables.items():
            for join in table["joins"]:
                with self.subTest(table=name, target=join["table"]):
                    target = tables[join["table"]]
                    self.assertIn(join["left"], table["columns"])
                    self.assertIn(join["right"], target["columns"])
                    self.assertIn(join["cardinality"], {"many_to_one", "one_to_many", "one_to_one"})

    def test_four_prediction_interfaces_are_declared(self):
        self.assertEqual(
            set(self.catalog["prediction_interfaces"]),
            {
                "late_order_risk_predictions.csv",
                "supplier_receipt_risk_predictions.csv",
                "production_completion_risk_predictions.csv",
                "quality_risk_predictions.csv",
            },
        )


if __name__ == "__main__":
    unittest.main()
