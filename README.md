# Manufacturing Control Tower Foundry Agent

This repository deploys a Microsoft Foundry prompt agent that uses Code Interpreter to analyze the synthetic manufacturing Gold snapshot. The data as-of date is fixed at `2026-09-15`; answers are analytical demo outputs, not live operational data.

## Setup

Authenticate with the company Azure account, restore the locked environment, and configure these values in the uncommitted `.env` file:

```powershell
az login
uv sync --frozen
```

```dotenv
FOUNDRY_PROJECT_ENDPOINT=https://<resource>.services.ai.azure.com/api/projects/<project>
FOUNDRY_MODEL_DEPLOYMENT=gpt-4.1-mini
FOUNDRY_AGENT_NAME=manufacturing-control-tower-agent
```

The deployment expects the 16 CSV files under `data/gold_snapshots/epic_soca_6rn73kkx4n/named-outputs/snapshot/csv/`. Four prediction files under `data/predictions/` are optional; missing predictions are reported as limitations and do not block the core demo.

## Deploy and use the Playground

```powershell
uv run python scripts/create_agent.py deploy
uv run python scripts/create_agent.py replace
uv run python scripts/create_agent.py cleanup
```

Use `deploy` for the first version. Use `replace` to create and validate a replacement before deleting the recorded prior version. Use `cleanup` only when the persistent demo agent is no longer needed.

After deployment, open Microsoft Foundry, go to **Build > Agents**, select `manufacturing-control-tower-agent`, and chat in the Playground. No separate chat application is required.

Suggested demo sequence:

1. Which active customer commitments are due in the next 14 days?
2. What operational signals explain the highest-risk commitments?
3. What recovery alternatives are available, including cost limitations and required approvers?
4. Show no more than 10 affected order lines.
5. Show the next 10 records using the same ranking.

The agent analyzes complete matching populations in Python while limiting model-visible output to 15 grouped rows, 10 detailed rows, and 12 columns. Recommendations remain proposals and require human approval.

## Validate

Run the local contract tests without Azure access:

```powershell
uv run python -m unittest discover -s tests -v
```

Run the connected golden evaluation against the recorded persistent deployment:

```powershell
uv run python scripts/evaluate_agent.py --smoke
uv run python scripts/evaluate_agent.py --case active_commitments_due_14d
uv run python scripts/evaluate_agent.py --all
```

The evaluator requires Code Interpreter for dataset claims, compares independently reviewed numeric oracles, checks required limitations and prohibited claims, and verifies the 10-record pagination cap. Concise results are saved to the ignored `.foundry/evaluation-results.json` file.

To validate Code Interpreter independently with the original disposable sales-order fixture:

```powershell
uv run python scripts/validate_code_interpreter.py
```

The disposable validation deletes its uploaded file and temporary agent version in a `finally` block. The persistent manufacturing agent and its recorded files are unaffected.
