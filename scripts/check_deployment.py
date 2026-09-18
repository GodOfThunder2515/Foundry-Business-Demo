# scripts/check_deployment.py

import os
import shutil
import subprocess

from dotenv import load_dotenv


load_dotenv()

resource = os.environ["FOUNDRY_RESOURCE"]
resource_group = os.environ["RESOURCE_GROUP"]

az_executable = shutil.which("az.cmd") or shutil.which("az")

command = [
    az_executable,
    "cognitiveservices",
    "account",
    "deployment",
    "show",
    "--name",
    resource,
    "--resource-group",
    resource_group,
    "--deployment-name",
    "analytics-agent-model",
    "--query",
    "properties.provisioningState",
    "-o",
    "tsv",
]

subprocess.run(
    command,
    check=True,
    shell=True,
)