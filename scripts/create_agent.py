import os
import sys
from pathlib import Path

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition
from azure.identity import DefaultAzureCredential
from azure.ai.projects.models import (
    PromptAgentDefinition,
    FunctionTool,
)
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from src.instructions import BUSINESS_ANALYTICS_INSTRUCTIONS


load_dotenv()

project_endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
model_deployment = os.environ["FOUNDRY_MODEL_DEPLOYMENT"]
agent_name = os.environ["FOUNDRY_AGENT_NAME"]


project = AIProjectClient(
    endpoint=project_endpoint,
    credential=DefaultAzureCredential(),
)

sales_tool = FunctionTool(
    name="get_sales_performance",
    description=(
        "Get company sales actuals, targets, and ML forecasts "
        "for all sales regions for a specified period. "
        "Use this tool whenever answering company-specific questions "
        "about regional sales performance, targets, or forecasts."
    ),
    parameters={
        "type": "object",
        "properties": {
            "period": {
                "type": "string",
                "description": (
                    "The period requested by the user, "
                    "for example 'next month'."
                ),
            },
        },
        "required": ["period"],
        "additionalProperties": False,
    },
    strict=True,
)

agent = project.agents.create_version(
    agent_name=agent_name,
    definition=PromptAgentDefinition(
        model=model_deployment,
        instructions=BUSINESS_ANALYTICS_INSTRUCTIONS,
        tools=[sales_tool],
    ),
)

print("Agent created successfully")
print(f"Name: {agent.name}")
print(f"Version: {agent.version}")
print(f"ID: {agent.id}")