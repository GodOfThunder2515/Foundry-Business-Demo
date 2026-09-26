# Foundry, local Parquet, and the Power Apps visual: feasibility note

Research date: 2026-09-23. Sources are current Microsoft Learn pages and the official `microsoft/data-formulator` repository.

## Decision

The proposed experience is feasible, but **a Microsoft Foundry Prompt Agent with managed Code Interpreter cannot directly analyze `.parquet` attachments today**. Parquet is not in the documented supported-file list. The one-day demo should keep the downloaded Gold Parquet as the local/source artifact, generate a small immutable CSV analysis snapshot plus a JSON manifest, upload those supported files to Foundry, and let Code Interpreter perform iterative Python analysis over them.

If direct Parquet execution is non-negotiable, use the existing client-side function-tool loop to run DuckDB/PyArrow locally. That works for the CLI, but a cloud Power App cannot call a developer laptop without another reachable API/gateway. Hosting such an execution service is a different architecture and is unnecessary for the one-day demo.

## What Foundry Code Interpreter actually provides

- Code Interpreter lets a Prompt Agent write and run Python iteratively in a Microsoft-managed sandbox. The Python SDK uploads an input with `openai.files.create(purpose="assistants", file=...)`, then attaches its file ID to `CodeInterpreterTool`; uploaded inputs are placed in Azure storage and made available to the sandbox. The REST/toolbox path mounts them at `/mnt/data/{file-id}-{original-filename}`. [Microsoft: Code Interpreter for Foundry agents](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/code-interpreter)
- The sandbox is not the user's PC. It runs in the Foundry project's Azure region, is isolated per session/conversation, has no outbound internet access, and does not inherit the agent subnet. A session is active for up to one hour with a 30-minute idle timeout. Attached files are available inside the runtime; generated files such as charts are returned as downloadable container outputs. [Microsoft: sandbox behavior](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/code-interpreter#sandboxed-execution-environment)
- The current supported-file table includes CSV, JSON, XLSX, ZIP and several document/image/code types, but **does not include Parquet**. Microsoft explicitly recommends checking that table when an upload fails. [Microsoft: supported Code Interpreter file types](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/code-interpreter#supported-file-types)
- A Prompt Agent upload can be at most 512 MB. Basic agent setup keeps uploads in Microsoft-managed storage; Standard setup keeps them in the customer's Azure Blob Storage. Both remain Azure-side rather than local. [Microsoft: Agent Service limits and storage](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/limits-quotas-regions)
- Code Interpreter has a fixed package set. Microsoft documents common data-science packages but does not promise `pyarrow`, `fastparquet`, or DuckDB. Although ZIP is accepted, wrapping Parquet in ZIP would still rely on an undocumented Parquet engine after extraction. Do not make that the demo's critical path. [Microsoft: Code Interpreter troubleshooting](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/code-interpreter#troubleshooting)

### Supported alternatives

1. **Recommended for the one-day demo:** locally derive one or a few focused CSV files from the Gold Parquet, upload them once, and attach their file IDs to the Prompt Agent. Add a small JSON manifest containing snapshot date, grain, units, source filenames, filter scope, and model/prediction version.
2. **CLI-only direct Parquet path:** expose one local function tool that runs bounded DuckDB queries over an allow-listed snapshot directory. The existing CLI tool-call loop can execute it, but the file never becomes reachable to a Power App merely because Foundry chose the tool call.
3. **Later, if direct Parquet is required from cloud clients:** host a small authenticated analysis API/container with DuckDB/PyArrow and put the snapshot in Blob/OneLake-accessible storage. Foundry's custom code interpreter is the documented escape hatch when managed Code Interpreter packages or isolation are insufficient. This is beyond the demo's minimum. [Microsoft: Code Interpreter guidance](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/code-interpreter)

## Where the files live in the recommended demo

```text
Fabric Gold / semantic model                 Power BI report visuals
          |
          | manual demo export
          v
Local versioned Gold Parquet (source artifact)
          |
          | deterministic projection/filter + CSV conversion
          v
Local CSV snapshot + manifest.json
          |
          | Foundry Files API, purpose=assistants
          v
Foundry file storage (managed in Basic; Blob in Standard)
          |
          | mounted into the Code Interpreter session
          v
Isolated Python sandbox -> grounded answer / optional generated chart
```

The Parquet is therefore **not exposed to Power BI through Foundry**. Power BI continues to show the governed Fabric/semantic-model data. The uploaded CSV is a separately versioned, explicitly static analytical snapshot for the demo agent.

## Power BI and Power Apps visual route

The Power Apps visual is a UI embedded in a Power BI report, not a data-access bridge into the Foundry sandbox.

- Add the relevant report fields (preferably order-line ID plus a few display/filter fields) to the Power Apps visual. In the canvas app they appear as the read-only `PowerBIIntegration.Data` source and update as report selections/filters change. It can pass at most 1,000 records. [Microsoft: Power Apps visual for Power BI](https://learn.microsoft.com/en-us/power-apps/maker/canvas-apps/powerapps-custom-visual)
- The app should send only the user's question and compact report context (for example selected `sales_order_line_id` values, plant, due-date window, and current as-of date). Do not send the full dataset; the agent already has the uploaded snapshot.
- A canvas-app button can invoke a Power Automate flow with `FlowName.Run(...)`, and the flow can return the agent answer for display in the app. [Microsoft: trigger a flow from a canvas app](https://learn.microsoft.com/en-us/power-apps/maker/canvas-apps/how-to/trigger-flow)
- The flow needs a secure HTTPS route to Foundry. The smallest maintainable route is a thin Entra-protected API (for example an Azure Function) that owns Foundry authentication and invokes the Foundry Responses API. Power Apps/Power Automate can call such a REST API through a custom connector; Microsoft documents this exact canvas app -> custom connector -> Entra-protected Azure Function pattern. [Microsoft: REST API from a canvas app](https://learn.microsoft.com/en-us/power-platform/architecture/reference-architectures/custom-connector-canvas)
- Foundry's Responses endpoint accepts an `agent_reference` and input; the Code Interpreter documentation includes the REST invocation shape. Preserve the returned conversation/response identifier in app state if multi-turn follow-ups are needed. [Microsoft: invoke a Prompt Agent through Responses](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/code-interpreter#create-a-chart-with-code-interpreter-using-the-rest-api)

Recommended interaction:

```text
Power BI filter/selection
  -> PowerBIIntegration.Data (<= 1,000 rows)
  -> Power Apps question + selected IDs
  -> Power Automate flow
  -> thin authenticated API
  -> Foundry Prompt Agent + already-attached snapshot
  -> answer returned to and displayed inside Power Apps visual
```

For the demo, display the answer inside the Power Apps visual and stop there. The visual cannot send data back to or filter the Power BI report, and report/data-source refresh from the app has restrictions: `PowerBIIntegration.Refresh()` requires an app created from the visual and a DirectQuery source. [Microsoft: Power Apps visual limitations](https://learn.microsoft.com/en-us/power-apps/maker/canvas-apps/powerapps-custom-visual#limitations-of-the-power-apps-visual)

If insights later need to become durable Power BI data, persist an approved structured result to a governed store (Fabric/Dataverse/SQL) and refresh/query it through the semantic model. That is a later feature, not required to show conversational analysis in the embedded app.

## What to borrow from Data Formulator—and what not to copy

Useful principles from the official project:

- Keep one unified analyst and one conversational thread for loading, questions, explanations, tables, and follow-ups rather than building a specialist-agent hierarchy. The project describes a unified `DataAgent`, persistent workspaces, and a Data Thread that preserves iterative exploration. [Microsoft Data Formulator repository](https://github.com/microsoft/data-formulator) and [0.7 release](https://github.com/microsoft/data-formulator/releases/tag/0.7.0)
- Separate durable workspace data from generated execution. Data Formulator stores uploaded files, Parquet tables, and metadata in a workspace, while generated Python runs in a sandbox. Its Docker sandbox mounts workspace data read-only and returns output through a separate artifact. [Data Formulator development architecture](https://github.com/microsoft/data-formulator/blob/main/DEVELOPMENT.md#sandbox)
- Keep provenance/lineage with the dataset. Data Formulator's workspace uses metadata alongside data files and supports local or Azure Blob backends. For this demo, one manifest JSON is enough; do not reproduce its workspace framework. [Data Formulator Azure Blob workspace](https://github.com/microsoft/data-formulator/blob/main/DEVELOPMENT.md#azure-blob-storage-workspace)
- Parquet plus DuckDB is a good implementation choice when **we control the runtime**. Data Formulator deliberately preloads pandas/numpy/DuckDB in its local sandbox and uses Parquet for workspace tables. That design does not imply the managed Foundry Code Interpreter accepts Parquet. [Data Formulator sandbox](https://github.com/microsoft/data-formulator/blob/main/DEVELOPMENT.md#sandbox)

Skip for this demo: Data Formulator's UI, branching graph, connector framework, persistent workspace service, chart grammar, report builder, multiple sandbox backends, source discovery, and agent hierarchy. The useful minimum is one agent, one immutable snapshot, one manifest, iterative Python, and evidence-bearing answers.

## Recommended proof before implementation planning

Run one small end-to-end spike:

1. Export a narrow Gold Parquet slice and deterministically convert it to CSV.
2. Upload CSV plus manifest and attach them to the existing Prompt Agent with Code Interpreter.
3. Ask one multi-step manufacturing question and verify all quantities against the source rows.
4. Call the same agent through a tiny authenticated endpoint, then from a Power Apps button using selected Power BI order-line IDs.

This proves the only uncertain integration seam without building the rest of Data Formulator.
