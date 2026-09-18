import os
import shutil
import subprocess

from dotenv import load_dotenv


load_dotenv()

resource = os.environ["FOUNDRY_RESOURCE"]
resource_group = os.environ["RESOURCE_GROUP"]

az_executable = shutil.which("az.cmd") or shutil.which("az")

if not az_executable:
    raise RuntimeError("Azure CLI not found.")

print(f"Using Azure CLI: {az_executable}")

command = [
    az_executable,
    "cognitiveservices",
    "account",
    "list-models",
    "-n",
    resource,
    "-g",
    resource_group,
    "--query",
    (
        "[?name=='DeepSeek-V4-Flash']."
        "{Name:name,Format:format,Version:version,SKUs:skus}"
    ),
    "-o",
    "json",
]

subprocess.run(
    command,
    check=True,
    shell=True,  # important on Windows for az.cmd
)