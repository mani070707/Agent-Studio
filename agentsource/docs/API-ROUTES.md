# API Routes — AgentSource

Base path: `/api`. All request/response bodies are JSON unless noted (`multipart/form-data` for
uploads, `text/event-stream` for the trace stream). All list endpoints support `?page=&size=`
pagination (default `size=20`); omitted below for brevity.

---

## Skills

| Method | Path | Request body | Response |
|---|---|---|---|
| GET | `/skills` | — | `Skill[]` |
| GET | `/skills/{id}` | — | `Skill` |
| POST | `/skills` | `{ name, body }` | `Skill` |
| PUT | `/skills/{id}` | `{ body }` | `Skill` |
| DELETE | `/skills/{id}` | — | `204` (fails `409` if referenced by any `agent_version`) |

## Schemas

| Method | Path | Request body | Response |
|---|---|---|---|
| GET | `/schemas` | — | `SchemaEntry[]` (filterable: `?kind=input\|output`) |
| GET | `/schemas/{id}` | — | `SchemaEntry` |
| POST | `/schemas` | `{ name, kind, jsonSchema }` | `SchemaEntry` |
| PUT | `/schemas/{id}` | `{ jsonSchema }` | `SchemaEntry` |
| DELETE | `/schemas/{id}` | — | `204` (fails `409` if referenced) |

## Prompts

| Method | Path | Request body | Response |
|---|---|---|---|
| GET | `/prompts` | — | `Prompt[]` with nested versions |
| POST | `/prompts` | `{ name }` | `Prompt` |
| POST | `/prompts/{id}/versions` | `{ body }` | `PromptVersion` (draft) |
| POST | `/prompts/{id}/versions/{versionId}/publish` | — | `PromptVersion` (published) |

## Platform tools

| Method | Path | Request body | Response |
|---|---|---|---|
| GET | `/tools/platform` | — | `PlatformTool[]` (read-only — populated by code at startup) |

## MCP servers & tools

| Method | Path | Request body | Response |
|---|---|---|---|
| GET | `/mcp-servers` | — | `McpServer[]` with nested `tools` |
| GET | `/mcp-servers/{id}` | — | `McpServer` |
| POST | `/mcp-servers` | `{ name, transport, baseUrl?, command?, authSecretRef? }` | `McpServer` (tools auto-discovered via `tools/list`) |
| POST | `/mcp-servers/{id}/refresh` | — | re-runs `tools/list`, syncs `mcp_tool` rows |
| DELETE | `/mcp-servers/{id}` | — | `204` |

## Connectors

| Method | Path | Request body | Response |
|---|---|---|---|
| GET | `/connectors` | — | `Connector[]` |
| POST | `/connectors` | `{ name, type, config, secretRef? }` | `Connector` |
| POST | `/connectors/{id}/test` | `{ sampleInput }` | `{ output }` or `4xx` with the upstream error surfaced |
| DELETE | `/connectors/{id}` | — | `204` |

## Agents

| Method | Path | Request body | Response |
|---|---|---|---|
| GET | `/agents` | — | `Agent[]` with nested versions summary |
| GET | `/agents/{id}` | — | `Agent` + full version list |
| POST | `/agents` | `{ name, description? }` | `Agent` |
| PUT | `/agents/{id}` | `{ name?, description? }` | `Agent` |
| DELETE | `/agents/{id}` | — | `204` (fails `409` if any version is published) |
| POST | `/agents/{id}/versions` | `{ harnessConfig, skillId, outputSchemaId, inputSchemaId? }` | `AgentVersion` (draft) — `409` if a draft already exists |
| GET | `/agents/{id}/versions/{versionId}` | — | `AgentVersion` |
| PUT | `/agents/{id}/versions/{versionId}` | `{ harnessConfig?, skillId?, outputSchemaId? }` | `AgentVersion` — `409` if already published |
| POST | `/agents/{id}/versions/{versionId}/publish` | — | `AgentVersion` (published) or `409 { reason: "evaluation_gate_not_passed", latestScore }` |
| POST | `/agents/{id}/versions/{versionId}/run` | `{ input? , documentId? }` | `202 { runId }` |

## Documents (generic file input)

| Method | Path | Request body | Response |
|---|---|---|---|
| POST | `/documents` | multipart `file` | `{ id, filename, contentType, storagePath }` |
| GET | `/documents/{id}` | — | document metadata |
| GET | `/documents/{id}/content` | — | raw file bytes, correct `Content-Type` |

## Workflows

| Method | Path | Request body | Response |
|---|---|---|---|
| GET | `/workflows` | — | `Workflow[]` with nested versions |
| POST | `/workflows` | `{ name }` | `Workflow` |
| POST | `/workflows/{id}/versions` | `{ steps }` (Tier 1) or `{ bpmnXml }` (Tier 2) | `WorkflowVersion` (draft) |
| POST | `/workflows/{id}/versions/{versionId}/publish` | — | `WorkflowVersion` (published) |
| POST | `/workflows/{id}/versions/{versionId}/run` | `{ input? }` | `202 { runId }` (or `{ runIds: [] }` if the workflow fans out to multiple agent runs) |

## Runs

| Method | Path | Request body | Response |
|---|---|---|---|
| GET | `/runs` | — | `Run[]` (filterable: `?agentVersionId=&status=`) |
| GET | `/runs/{id}` | — | `Run` (status, output, error) |
| GET | `/runs/{id}/trace` | — | `RunTrace[]` (full history, non-streaming — for a completed run) |
| GET | `/runs/{id}/trace/stream` | — | `text/event-stream`, one SSE `data:` frame per `RunTrace` row, in `seq_no` order, connection closes after the terminal `RUN_COMPLETED`/`RUN_FAILED` event |

## Evaluation

| Method | Path | Request body | Response |
|---|---|---|---|
| GET | `/evaluation-datasets` | — | `EvaluationDataset[]` with case counts |
| POST | `/evaluation-datasets` | `{ name }` | `EvaluationDataset` |
| POST | `/evaluation-datasets/{id}/cases` | `{ input?, documentId?, expectedOutput }` | `EvaluationCase` |
| POST | `/agents/{id}/versions/{versionId}/evaluate` | `{ evaluationDatasetId, threshold? }` | `EvaluationRun` (`{ passCount, failCount, score, status }`) |
| GET | `/agents/{id}/versions/{versionId}/evaluations` | — | `EvaluationRun[]`, most recent first |

---

## Error shape (all non-2xx responses)

```json
{ "error": "evaluation_gate_not_passed", "message": "Latest evaluation score 0.72 is below threshold 0.9", "details": { } }
```

## Auth (out of scope for the MVP, noted for extension)

The MVP ships with no auth — it's a local/demo platform. If extending: put a bearer-token check in
a single Spring filter in `app`, and it applies uniformly to every route above with zero changes to
individual controllers, since none of them assume an authenticated principal today.
