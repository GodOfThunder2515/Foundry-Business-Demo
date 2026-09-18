import json
import os
import sys
from pathlib import Path

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv
from openai.types.responses.response_input_param import (
    FunctionCallOutput,
)


ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from src.tools.business_data import get_sales_performance


load_dotenv()

project_endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
agent_name = os.environ["FOUNDRY_AGENT_NAME"]


project = AIProjectClient(
    endpoint=project_endpoint,
    credential=DefaultAzureCredential(),
)

openai = project.get_openai_client()

conversation = openai.conversations.create()

print(f"Connected to agent: {agent_name}")
print(f"Conversation ID: {conversation.id}")
print("Type 'exit' to quit.")
print()


def ask_agent(user_input: str):

    response = openai.responses.create(
        conversation=conversation.id,
        input=user_input,
        extra_body={
            "agent_reference": {
                "name": agent_name,
                "type": "agent_reference",
            }
        },
    )

    # Keep looping in case the agent makes one or more tool calls.
    while True:

        tool_outputs = []

        for item in response.output:

            if item.type != "function_call":
                continue

            print(f"[Tool requested] {item.name}")

            arguments = json.loads(item.arguments)

            if item.name == "get_sales_performance":

                result = get_sales_performance(
                    **arguments
                )

                print(
                    "[Tool result]",
                    json.dumps(result, indent=2),
                )

                tool_outputs.append(
                    FunctionCallOutput(
                        type="function_call_output",
                        call_id=item.call_id,
                        output=json.dumps(result),
                    )
                )

            else:
                raise RuntimeError(
                    f"Unknown tool requested: {item.name}"
                )

        # No tool calls means we have the final response.
        if not tool_outputs:
            return response.output_text

        # Give tool results back to the agent.
        response = openai.responses.create(
            conversation=conversation.id,
            input=tool_outputs,
            extra_body={
                "agent_reference": {
                    "name": agent_name,
                    "type": "agent_reference",
                }
            },
        )


while True:

    user_input = input("You: ").strip()

    if user_input.lower() in {"exit", "quit"}:
        break

    if not user_input:
        continue

    answer = ask_agent(user_input)

    print()
    print(f"Agent: {answer}")
    print()