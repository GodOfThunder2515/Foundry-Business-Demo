import json
import os
from pathlib import Path

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    PromptAgentDefinition,
    CodeInterpreterTool,
    AutoCodeInterpreterToolParam,
)
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

load_dotenv()


PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
MODEL_DEPLOYMENT = os.environ["FOUNDRY_MODEL_DEPLOYMENT"]

AGENT_NAME = "manufacturing-insight-poc"

MANIFEST_PATH = Path("foundry_file_manifest.json")


# ---------------------------------------------------------------------
# LOAD EXISTING FILE IDS
# ---------------------------------------------------------------------

manifest = json.loads(
    MANIFEST_PATH.read_text(encoding="utf-8")
)

file_ids = manifest["file_ids"]

print(f"Using {len(file_ids)} existing Foundry files.")

for filename, info in manifest["files"].items():
    print(f"  {filename:<40} {info['file_id']}")


# ---------------------------------------------------------------------
# TEMPORARY POC INSTRUCTIONS
# ---------------------------------------------------------------------
# We'll replace these with the full finalized instruction payload next.
# For now, the goal is simply to prove:
#   1. all files mount correctly
#   2. dataset_catalog.json can be read
#   3. analysis_helper.py can be imported/read
#   4. Code Interpreter can selectively analyze the CSVs

instructions = """
You are a manufacturing data analysis agent.

You have access to manufacturing CSV datasets, dataset_catalog.json,
and analysis_helper.py through Code Interpreter.

For any question about the supplied manufacturing data:

1. Use Code Interpreter.
2. Inspect dataset_catalog.json before making assumptions about schemas.
3. Identify the minimum relevant tables.
4. Load only the required columns where practical.
5. Perform calculations over the complete matching population.
6. Do not invent columns, joins, metrics, or business facts.
7. Do not print entire dataframes or large raw datasets.

For this first validation version, when asked about available data,
use Python to inspect the mounted files and dataset catalog rather than
answering from memory.
"""


# ---------------------------------------------------------------------
# CREATE AGENT VERSION
# ---------------------------------------------------------------------

project = AIProjectClient(
    endpoint=PROJECT_ENDPOINT,
    credential=DefaultAzureCredential(),
)

agent = project.agents.create_version(
    agent_name=AGENT_NAME,
    definition=PromptAgentDefinition(
        model=MODEL_DEPLOYMENT,
        instructions=instructions,
        tools=[
            CodeInterpreterTool(
                container=AutoCodeInterpreterToolParam(
                    file_ids=file_ids
                )
            )
        ],
    ),
    description=(
        "Manufacturing insight POC using existing Gold CSV files "
        "with built-in Code Interpreter."
    ),
)


print("\n" + "=" * 80)
print("AGENT VERSION CREATED")
print("=" * 80)

print(f"Agent name : {agent.name}")
print(f"Version    : {agent.version}")
print(f"Files      : {len(file_ids)}")

print("\n✅ No files were uploaded.")
print("✅ Existing Foundry file IDs were reused.")
print("✅ Code Interpreter is configured with the 18 canonical files.")