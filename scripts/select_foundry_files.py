import json
import os
from pathlib import Path

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential

from dotenv import load_dotenv

load_dotenv()


# ---------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------

PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]

# These are the ONLY files we want available to Code Interpreter.
REQUIRED_FILES = {
    # Facts
    "fact_sales.csv",
    "fact_shipments.csv",
    "fact_inventory_lots.csv",
    "fact_inventory_transactions.csv",
    "fact_material_reservations.csv",
    "fact_operations_snapshot.csv",
    "fact_procurement.csv",
    "fact_quality_inspections.csv",
    "fact_quality_nonconformances.csv",
    "fact_finance.csv",

    # Dimensions
    "dim_customer.csv",
    "dim_date.csv",
    "dim_product.csv",
    "dim_region.csv",
    "dim_supplier.csv",
    "dim_warehouse.csv",

    # Code Interpreter support files
    "dataset_catalog.json",
    "analysis_helper.py",
}


# ---------------------------------------------------------------------
# CONNECT
# ---------------------------------------------------------------------

credential = DefaultAzureCredential()

project = AIProjectClient(
    endpoint=PROJECT_ENDPOINT,
    credential=credential,
)

openai = project.get_openai_client()


# ---------------------------------------------------------------------
# GET EXISTING FOUNDRY FILES
# ---------------------------------------------------------------------

print("=" * 80)
print("READING EXISTING FOUNDRY FILES")
print("=" * 80)

all_files = list(openai.files.list())

print(f"\nFound {len(all_files)} uploaded Foundry files.")


# ---------------------------------------------------------------------
# GROUP REQUIRED FILES BY ORIGINAL FILENAME
# ---------------------------------------------------------------------

by_filename = {}

for file in all_files:
    filename = file.filename

    if filename not in REQUIRED_FILES:
        continue

    by_filename.setdefault(filename, []).append(file)


# ---------------------------------------------------------------------
# SELECT NEWEST COPY OF EACH FILE
# ---------------------------------------------------------------------

selected = {}
duplicates = {}

for filename in sorted(REQUIRED_FILES):
    candidates = by_filename.get(filename, [])

    if not candidates:
        continue

    # newest upload wins
    candidates = sorted(
        candidates,
        key=lambda f: f.created_at or 0,
        reverse=True,
    )

    selected[filename] = candidates[0]

    if len(candidates) > 1:
        duplicates[filename] = candidates[1:]


# ---------------------------------------------------------------------
# VALIDATE
# ---------------------------------------------------------------------

missing = sorted(REQUIRED_FILES - set(selected))

print("\n" + "=" * 80)
print("CANONICAL FILES SELECTED")
print("=" * 80)

for filename in sorted(selected):
    file = selected[filename]

    size_mb = (file.bytes or 0) / (1024 * 1024)

    print(
        f"{filename:<40} "
        f"{file.id:<45} "
        f"{size_mb:>8.2f} MB"
    )


# ---------------------------------------------------------------------
# SHOW DUPLICATES WE ARE IGNORING
# ---------------------------------------------------------------------

print("\n" + "=" * 80)
print("DUPLICATES IGNORED")
print("=" * 80)

if not duplicates:
    print("No duplicates found.")
else:
    for filename, files in sorted(duplicates.items()):
        print(f"\n{filename}")

        print(f"  KEEP   : {selected[filename].id}")

        for file in files:
            print(f"  IGNORE : {file.id}")


# ---------------------------------------------------------------------
# SHOW MISSING FILES
# ---------------------------------------------------------------------

print("\n" + "=" * 80)
print("VALIDATION")
print("=" * 80)

if missing:
    print("\n❌ Missing required files:")

    for filename in missing:
        print(f"  - {filename}")

    raise SystemExit(
        "\nStopping because the complete canonical file set is not available."
    )

print(f"\n✅ All {len(REQUIRED_FILES)} required files are available.")
print(f"✅ Selected exactly {len(selected)} canonical files.")
print("✅ Duplicate uploads will NOT be attached to the agent.")


# ---------------------------------------------------------------------
# WRITE MANIFEST FOR THE NEXT STEP
# ---------------------------------------------------------------------

manifest = {
    "files": {
        filename: {
            "file_id": file.id,
            "filename": filename,
            "bytes": file.bytes,
            "created_at": file.created_at,
        }
        for filename, file in sorted(selected.items())
    },
    "file_ids": [
        selected[filename].id
        for filename in sorted(selected)
    ],
}


output_path = Path("foundry_file_manifest.json")

output_path.write_text(
    json.dumps(manifest, indent=2),
    encoding="utf-8",
)

print(f"\nManifest written to:")
print(output_path.resolve())

print("\nFile IDs that will eventually be attached to Code Interpreter:")
for file_id in manifest["file_ids"]:
    print(f"  {file_id}")