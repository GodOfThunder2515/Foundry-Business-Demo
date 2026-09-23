import json
import tempfile
import unittest
from pathlib import Path

from src.agent_assets import collect_upload_paths, compose_instructions


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "knowledge/dataset_catalog.json"


class ComposeInstructionsTests(unittest.TestCase):
    def make_assets(self, root: Path, table_context: str = "TABLE_TOKEN") -> tuple[Path, Path]:
        knowledge = root / "knowledge"
        knowledge.mkdir()
        (knowledge / "business_context.md").write_text("BUSINESS_TOKEN", encoding="utf-8")
        (knowledge / "table_context.md").write_text(table_context, encoding="utf-8")
        (knowledge / "analysis_examples.md").write_text("EXAMPLE_TOKEN", encoding="utf-8")
        instructions = root / "agent_instructions.md"
        instructions.write_text("CORE_TOKEN", encoding="utf-8")
        return knowledge, instructions

    def test_composes_each_section_once_in_required_order(self):
        with tempfile.TemporaryDirectory() as directory:
            knowledge, instructions = self.make_assets(Path(directory))

            result = compose_instructions(knowledge, instructions)

            self.assertEqual(result.count("CORE_TOKEN"), 1)
            self.assertEqual(result.count("BUSINESS_TOKEN"), 1)
            self.assertEqual(result.count("TABLE_TOKEN"), 1)
            self.assertEqual(result.count("EXAMPLE_TOKEN"), 1)
            self.assertLess(result.index("CORE_TOKEN"), result.index("BUSINESS_TOKEN"))
            self.assertLess(result.index("BUSINESS_TOKEN"), result.index("TABLE_TOKEN"))
            self.assertLess(result.index("TABLE_TOKEN"), result.index("EXAMPLE_TOKEN"))

    def test_rejects_table_context_over_12000_characters(self):
        with tempfile.TemporaryDirectory() as directory:
            knowledge, instructions = self.make_assets(Path(directory), "x" * 12001)

            with self.assertRaisesRegex(ValueError, "12,000"):
                compose_instructions(knowledge, instructions)

    def test_missing_instruction_asset_fails_clearly(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            knowledge, instructions = self.make_assets(root)
            (knowledge / "business_context.md").unlink()

            with self.assertRaisesRegex(FileNotFoundError, "business_context.md"):
                compose_instructions(knowledge, instructions)


class CollectUploadsTests(unittest.TestCase):
    def create_required_files(self, root: Path) -> tuple[Path, Path, Path]:
        gold = root / "gold"
        gold.mkdir()
        catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
        for table in catalog["tables"].values():
            (gold / table["filename"]).touch()
        helper = root / "analysis_helper.py"
        helper.touch()
        catalog_copy = root / "dataset_catalog.json"
        catalog_copy.write_text(json.dumps(catalog), encoding="utf-8")
        return gold, helper, catalog_copy

    def test_collects_16_gold_files_plus_helper_and_catalog(self):
        with tempfile.TemporaryDirectory() as directory:
            gold, helper, catalog = self.create_required_files(Path(directory))

            paths, warnings = collect_upload_paths(gold, helper, catalog)

            self.assertEqual(len(paths), 18)
            self.assertEqual(len(warnings), 4)
            self.assertTrue(all("Optional prediction file not found" in warning for warning in warnings))

    def test_missing_gold_file_prevents_upload(self):
        with tempfile.TemporaryDirectory() as directory:
            gold, helper, catalog = self.create_required_files(Path(directory))
            (gold / "fact_sales.csv").unlink()

            with self.assertRaisesRegex(FileNotFoundError, "fact_sales.csv"):
                collect_upload_paths(gold, helper, catalog)

    def test_present_predictions_are_appended_and_missing_ones_warn(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            gold, helper, catalog = self.create_required_files(root)
            predictions = root / "predictions"
            predictions.mkdir()
            prediction = predictions / "late_order_risk_predictions.csv"
            prediction.touch()

            paths, warnings = collect_upload_paths(gold, helper, catalog, predictions)

            self.assertEqual(len(paths), 19)
            self.assertEqual(paths[-1], prediction)
            self.assertEqual(len(warnings), 3)

    def test_missing_helper_or_catalog_fails_before_upload(self):
        with tempfile.TemporaryDirectory() as directory:
            gold, helper, catalog = self.create_required_files(Path(directory))
            helper.unlink()

            with self.assertRaisesRegex(FileNotFoundError, "analysis_helper.py"):
                collect_upload_paths(gold, helper, catalog)


if __name__ == "__main__":
    unittest.main()
