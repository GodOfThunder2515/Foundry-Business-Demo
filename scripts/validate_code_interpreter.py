import csv
import json
import os
import tempfile
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    AutoCodeInterpreterToolParam,
    CodeInterpreterTool,
    PromptAgentDefinition,
)
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/raw/manufacturing_order_inventory_dataset/sales_orders.csv"
ACTIVE_STATUSES = {"open", "on_hold", "partially_shipped"}
START_DATE = date(2026, 9, 15)
END_DATE = date(2026, 9, 29)
ROW_LIMIT = 1_000
EXPECTED = {
    "row_count": 537,
    "total_order_value": Decimal("6612240.06"),
    "total_order_qty": 46_849,
    "backordered_count": 536,
    "on_hold_count": 100,
    "highest_value_order_id": "SO000029062",
    "highest_value_order_value": Decimal("120609.47"),
}


def build_snapshot(source: Path, destination: Path) -> dict[str, Any]:
    rows: list[dict[str, str]] = []

    with source.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"CSV has no header: {source}")

        for row in reader:
            promised_date = date.fromisoformat(row["promised_ship_date"])
            if (
                row["order_status"] in ACTIVE_STATUSES
                and START_DATE <= promised_date < END_DATE
            ):
                rows.append(row)
                if len(rows) == ROW_LIMIT:
                    break

    if not rows:
        raise ValueError("No sales orders matched the validation filter")

    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=reader.fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    highest = max(rows, key=lambda row: Decimal(row["total_order_value"]))
    return {
        "row_count": len(rows),
        "total_order_value": sum(
            (Decimal(row["total_order_value"]) for row in rows), Decimal("0")
        ).quantize(Decimal("0.01")),
        "total_order_qty": sum(int(Decimal(row["total_order_qty"])) for row in rows),
        "backordered_count": sum(row["backorder_flag"] == "Y" for row in rows),
        "on_hold_count": sum(row["order_status"] == "on_hold" for row in rows),
        "highest_value_order_id": highest["sales_order_id"],
        "highest_value_order_value": Decimal(highest["total_order_value"]).quantize(
            Decimal("0.01")
        ),
    }


def extract_json(text: str) -> dict[str, Any]:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end < start:
        raise ValueError("Agent response did not contain a JSON object")
    value = json.loads(text[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("Agent response JSON was not an object")
    return value


def result_errors(actual: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key, expected in EXPECTED.items():
        if key not in actual:
            errors.append(f"{key}: missing")
            continue
        value = actual[key]
        if isinstance(expected, Decimal):
            try:
                value = Decimal(str(value)).quantize(Decimal("0.01"))
            except InvalidOperation:
                pass
        if value != expected:
            errors.append(f"{key}: expected {expected}, got {actual[key]}")
    return errors


def main() -> int:
    load_dotenv()
    file_descriptor, temp_name = tempfile.mkstemp(
        prefix="foundry-sales-orders-", suffix=".csv"
    )
    os.close(file_descriptor)
    snapshot_path = Path(temp_name)
    uploaded_file = None
    agent = None
    failures: list[str] = []

    try:
        local_result = build_snapshot(SOURCE, snapshot_path)
        local_errors = result_errors(local_result)
        if local_errors:
            print("FAIL: local dataset does not match the fixed oracle")
            for error in local_errors:
                print(f"- {error}")
            return 1

        print(f"Local snapshot verified: {local_result['row_count']} rows")

        project_endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
        model_deployment = os.environ["FOUNDRY_MODEL_DEPLOYMENT"]
        agent_name = f"{os.environ['FOUNDRY_AGENT_NAME']}-ci-smoke"

        with (
            DefaultAzureCredential() as credential,
            AIProjectClient(
                endpoint=project_endpoint,
                credential=credential,
            ) as project,
            project.get_openai_client() as openai,
        ):
            try:
                with snapshot_path.open("rb") as snapshot:
                    uploaded_file = openai.files.create(
                        purpose="assistants",
                        file=snapshot,
                    )

                agent = project.agents.create_version(
                    agent_name=agent_name,
                    definition=PromptAgentDefinition(
                        model=model_deployment,
                        instructions=(
                            "You are a validation agent. Always use Code Interpreter and "
                            "Python to inspect the attached CSV. Never estimate values."
                        ),
                        tools=[
                            CodeInterpreterTool(
                                container=AutoCodeInterpreterToolParam(
                                    file_ids=[uploaded_file.id]
                                )
                            )
                        ],
                    ),
                    description="Disposable Code Interpreter CSV smoke test",
                )

                response = openai.responses.create(
                    input=(
                        "Use Python Code Interpreter to analyze the attached CSV. Return "
                        "only one JSON object with these keys: row_count, "
                        "total_order_value, total_order_qty, backordered_count, "
                        "on_hold_count, highest_value_order_id, and "
                        "highest_value_order_value. Sum the total_order_value and "
                        "total_order_qty columns; count backorder_flag == 'Y'; count "
                        "order_status == 'on_hold'; and identify the row with the maximum "
                        "total_order_value. Do not calculate from values in this prompt."
                    ),
                    extra_body={
                        "agent_reference": {
                            "name": agent.name,
                            "type": "agent_reference",
                        }
                    },
                )

                if not any(
                    getattr(item, "type", None) == "code_interpreter_call"
                    for item in response.output
                ):
                    failures.append("the response contained no code_interpreter_call")

                agent_result = extract_json(response.output_text)
                failures.extend(result_errors(agent_result))
            except Exception as error:
                failures.append(f"{type(error).__name__}: {error}")
            finally:
                if agent is not None:
                    try:
                        project.agents.delete_version(
                            agent_name=agent.name,
                            agent_version=agent.version,
                        )
                    except Exception as error:
                        failures.append(f"agent cleanup failed: {error}")
                if uploaded_file is not None:
                    try:
                        openai.files.delete(uploaded_file.id)
                    except Exception as error:
                        failures.append(f"file cleanup failed: {error}")
    except Exception as error:
        failures.append(f"{type(error).__name__}: {error}")
    finally:
        snapshot_path.unlink(missing_ok=True)

    if failures:
        print("FAIL: Foundry Code Interpreter validation")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("PASS: Foundry Code Interpreter used the CSV and matched the local oracle")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
