# API Routes — Agent Studio (this implementation)

All routes except `/health` and `/internal/*` require `Authorization: Bearer <supabase-jwt>`.
Every list/get/update/delete is scoped to the authenticated user — there is no cross-tenant
access. `/internal/*` requires `X-Internal-Cron-Secret` instead (no user JWT).

## Health

| Method | Path | Notes |
|---|---|---|
| GET | `/health` | No auth. Liveness check. |

## Skills

| Method | Path | Body / Notes |
|---|---|---|
| GET | `/skills` | List the caller's skills |
| POST | `/skills` | `{name, system_prompt, user_prompt_template}` |
| GET | `/skills/{id}` | |
| PUT | `/skills/{id}` | Rejected with `409` if `is_published` — create a new skill instead |
| POST | `/skills/{id}/publish` | Marks the skill immutable |
| DELETE | `/skills/{id}` | |

## Schemas

| Method | Path | Body / Notes |
|---|---|---|
| GET | `/schemas` | |
| POST | `/schemas` | `{name, kind: "input"|"output", json_schema}` — validated as a real JSON Schema (Draft 2020-12) |
| GET | `/schemas/{id}` | |
| DELETE | `/schemas/{id}` | |

## Secrets (BYOK)

| Method | Path | Body / Notes |
|---|---|---|
| GET | `/secrets` | Returns `{id, name}` only — never the value |
| POST | `/secrets` | `{name, value}` — encrypted at rest (Fernet) |
| DELETE | `/secrets/{id}` | |

## Platform tools

| Method | Path | Notes |
|---|---|---|
| GET | `/tools/platform` | Lists built-in tools (`calculator`, `url_fetch`, `web_search`, `search_documents`), synced from code at startup |

## MCP servers

| Method | Path | Body / Notes |
|---|---|---|
| GET | `/mcp-servers` | |
| POST | `/mcp-servers` | `{name, url, secret_ref?}` — immediately calls `tools/list` on the server and syncs `mcp_tool` rows |
| POST | `/mcp-servers/{id}/sync` | Re-discover tools |
| GET | `/mcp-servers/{id}/tools` | |
| DELETE | `/mcp-servers/{id}` | Cascades its `mcp_tool` rows |

## Connectors

| Method | Path | Body / Notes |
|---|---|---|
| GET | `/connectors` | |
| POST | `/connectors` | `{name, base_url, auth_secret_ref?, request_template}` |
| GET | `/connectors/{id}` | |
| POST | `/connectors/{id}/test` | `{variables: {...}}` — executes the connector for real, SSRF-guarded |
| DELETE | `/connectors/{id}` | |

## Content store

| Method | Path | Body / Notes |
|---|---|---|
| GET | `/content?agent_id=` | |
| POST | `/content?agent_id=` | multipart `file` upload — stored in Supabase Storage, text extracted (PDF/txt), max 20MB |
| DELETE | `/content/{id}` | |

## Agents

| Method | Path | Body / Notes |
|---|---|---|
| GET | `/agents` | |
| POST | `/agents` | `{name, agent_type, domain, owner, tags, description}` |
| GET | `/agents/{id}` | |
| PUT | `/agents/{id}` | Partial update — e.g. `{evaluation_gate_enabled: true}` |
| DELETE | `/agents/{id}` | Cascades its versions |
| GET | `/agents/{id}/versions` | |
| POST | `/agents/{id}/versions` | Creates a draft. `409` if a draft already exists; `400` if any tool/mcp-tool/connector/skill/schema referenced isn't owned by the caller |
| GET | `/agents/{id}/versions/{version_id}` | |
| PUT | `/agents/{id}/versions/{version_id}` | `409` if the version is already published |
| POST | `/agents/{id}/versions/{version_id}/publish` | `409` with `{reason: "evaluation_gate_not_passed"}` if the gate is enabled and not passed |

## Triggers

| Method | Path | Body / Notes |
|---|---|---|
| GET | `/agents/{agent_id}/triggers` | |
| POST | `/agents/{agent_id}/triggers` | `{name, type: "manual"|"api"|"schedule", config, enabled}` — `schedule` requires `config.cron_expr` |
| PUT | `/agents/{agent_id}/triggers/{id}` | |
| DELETE | `/agents/{agent_id}/triggers/{id}` | |

## Runs

| Method | Path | Body / Notes |
|---|---|---|
| POST | `/agents/{agent_id}/versions/{version_id}/run` | `{input: {...}}` — runs **synchronously**, returns the completed `Run` |
| GET | `/runs?agent_id=` | List, optionally filtered |
| GET | `/runs/{id}` | |
| GET | `/runs/{id}/steps` | Ordered trace |

## Evaluation

| Method | Path | Body / Notes |
|---|---|---|
| POST | `/agents/{agent_id}/evaluation-datasets` | `{name, threshold}` |
| GET | `/agents/{agent_id}/evaluation-datasets` | |
| POST | `/evaluation-datasets/{id}/cases` | `{input, expected_output, compare_fields}` |
| GET | `/evaluation-datasets/{id}/cases` | |
| POST | `/agents/{agent_id}/versions/{version_id}/evaluate?dataset_id=` | Runs every case through the executor, scores, gates future publishes if enabled |

## Internal (cron only)

| Method | Path | Body / Notes |
|---|---|---|
| POST | `/internal/run-due-schedules` | Header `X-Internal-Cron-Secret`. Scans `schedule`-type triggers, runs any that are due against their agent's published version. |
