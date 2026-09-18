import os
import shutil
import subprocess

from dotenv import load_dotenv


load_dotenv()

resource = os.environ["FOUNDRY_RESOURCE"]
resource_group = os.environ["RESOURCE_GROUP"]

deployment_name = "analytics-agent-model"

az_executable = shutil.which("az.cmd") or shutil.which("az")

if not az_executable:
    raise RuntimeError("Azure CLI not found.")

command = [
    az_executable,
    "cognitiveservices",
    "account",
    "deployment",
    "create",
    "--name",
    resource,
    "--resource-group",
    resource_group,
    "--deployment-name",
    deployment_name,
    "--model-name",
    "DeepSeek-V4-Flash",
    "--model-version",
    "2026-04-23",
    "--model-format",
    "DeepSeek",
    "--sku-name",
    "GlobalStandard",
    "--sku-capacity",
    "1",
]

print("Deploying model...")
print(f"Deployment name: {deployment_name}")

subprocess.run(
    command,
    check=True,
    shell=True,
)

print()
print("Model deployment created successfully.")