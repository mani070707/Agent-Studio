# Low-Level Design — AgentSource

Companion to `HLD.md`. Database schema is in `DB-SCHEMA.sql`. This document covers module
internals, interfaces, and the two core execution sequences (publish, run) in enough detail that
no other reference material is needed to implement them.

---

## 1. Repository layout

```
agentsource/
├── docker-compose.yml
├── .env.example
├── README.md
├── docs/
│   ├── HLD.md
│   ├── LLD.md
│   ├── DB-SCHEMA.sql
│   ├── API-ROUTES.md
│   ├── UI-COMPONENTS.md
│   └── BUILD-PLAN.md
├── examples/
│   ├── harness-config.example.json
│   ├── output-schema.example.json
│   ├── skill-prompt.example.md
│   └── workflow.example.bpmn
├── mcp-server-example/              # a minimal self-hosted MCP server, standalone service
│   ├── package.json
│   └── src/server.ts
├── backend/
│   ├── pom.xml
│   ├── app/                         # Spring Boot entrypoint + Flyway migrations (DB-SCHEMA.sql goes here as V1__init.sql)
│   ├── common/                      # SecretResolver, provider interfaces, shared DTOs
│   ├── skills/
│   ├── schema-registry/
│   ├── prompts/
│   ├── tools/                       # platform tool implementations + registry
│   ├── mcp/                         # MCP client + mcp_server/mcp_tool registry
│   ├── connectors/
│   ├── agents/
│   ├── workflow/
│   ├── runs/                        # executor + SSE stream
│   └── evaluation/
└── ui/
    ├── package.json
    └── src/
        ├── screens/
        ├── components/
        └── lib/
```

Each backend module is its own Maven module with its own `pom.xml`, assembling into `app`.

---

## 2. Provider abstraction (module: `common`)

Three interfaces, each with a mock and a real implementation, selected by Spring profile
(`mock` vs `live`) so the platform runs fully offline except for the LLM call in `live` mode.

```java
public interface ModelProvider {
  ModelResponse complete(ModelRequest request); // request includes a forced JSON schema
}

public interface McpClient {
  List<McpToolDescriptor> listTools(McpServerConfig server);
  JsonNode callTool(McpServerConfig server, String toolName, JsonNode arguments);
}

public interface ConnectorExecutor {
  JsonNode execute(ConnectorConfig connector, JsonNode input);
}
```

`ModelProvider`'s mock implementation returns a canned response matching whatever output schema
was requested, with a simulated 300–800ms delay — enough to develop and demo the entire trace UI
and evaluation flow without spending on real model calls, then flip one profile flag to go live.

---

## 3. Secret resolution (module: `common`)

```java
public interface SecretResolver {
  Optional<String> resolve(String secretRef);
}
```

Default implementation checks, in order: (1) the `secret` table by `name`, (2) `System.getenv(name)`.
Nothing in the codebase ever logs a resolved secret value — `toString()`/`equals()` on any config
DTO holding a `secretRef` must print the ref name, never the resolved value.

---

## 4. MCP tool discovery and invocation (module: `mcp`)

- `POST /mcp-servers` (see `API-ROUTES.md`) stores the server config, then immediately calls
  `McpClient.listTools()` and inserts one `mcp_tool` row per tool returned — this is how the
  registry stays in sync with what a server actually exposes, rather than being hand-entered.
- At run time, the executor (module `runs`) resolves each `mcpToolAllowlist` entry in an agent
  version's harness config to its `mcp_server_id` via `mcp_tool.tool_name`, then calls
  `McpClient.callTool()`.
- Transport support: `http` (MCP streamable HTTP — the simplest to self-host, no process
  management needed) is the default; `stdio` is supported for local dev tool servers but not
  needed for the Docker Compose demo.

---

## 5. Platform tools (module: `tools`)

A platform tool is a Spring bean implementing:

```java
public interface PlatformTool {
  String name();                       // must match the platform_tool.name row
  JsonNode invoke(JsonNode input, Map<String, Object> args);
}
```

On startup, a `PlatformToolRegistry` collects all `PlatformTool` beans and upserts their
`platform_tool` row (name + declared schemas) — so the registry is always in sync with what code
actually exists, never hand-maintained separately from the implementation.

There is no required built-in tool — the platform ships with zero domain tools. A concrete example
tool (a PDF-to-structured-layout parser) is described separately in `examples/` for anyone building
the sample document-checking agent, but it is not part of the core platform.

---

## 6. Harness config shape (stored as `agent_version.harness_config`)

```json
{
  "toolAllowlist": ["<platform_tool.name>", "..."],
  "mcpToolAllowlist": ["<mcp_tool.tool_name>", "..."],
  "connectorAllowlist": ["<connector.name>", "..."],
  "model": { "provider": "anthropic", "model": "claude-sonnet-5", "temperature": 0 }
}
```

The runtime executor refuses to call any tool, MCP tool, or connector not present in the relevant
allowlist — this is enforced server-side in `runs`, not just hidden in the UI.

---

## 7. Publish sequence (modules: `agents`, `evaluation`)

1. Client calls `POST /agents/{id}/versions/{versionId}/publish`.
2. Handler queries `agent_version_publish_status` (the view in `DB-SCHEMA.sql`) for that version.
3. If `latest_evaluation_status != 'passed'` → `409 Conflict` with `{ "reason": "evaluation_gate_not_passed", "latestScore": ... }`.
4. If passed → set `is_published = true`, `published_at = now()`. Publishing a new version does
   **not** unpublish a previous version automatically — callers choose which published version to
   invoke by id, so a rollback is just "call the previous version's id again," no data migration
   needed.
5. `agent_version` rows are otherwise immutable after `is_published = true` — the API rejects any
   `PUT`/`PATCH` on a published version; edits require creating a new draft version.

## 8. Run execution sequence (module: `runs`)

Triggered by `POST /agents/{id}/versions/{versionId}/run` (direct) or as a workflow step (Tier 1
executor iterating `workflow_version.steps`).

1. Insert `run` row, `status = 'pending'`. Return `{ runId }` to the caller immediately.
2. Background task sets `status = 'running'`, `started_at = now()`, emits `RUN_STARTED`.
3. For each tool in `toolAllowlist` the skill's prompt logic calls (the LLM decides which, and in
   what order, via standard tool-calling — the executor just dispatches whatever the model
   requests): emit `TOOL_CALL_STARTED` → invoke `PlatformToolRegistry` → emit
   `TOOL_CALL_COMPLETED` with the output.
4. Same pattern for MCP tools (`MCP_TOOL_CALL_STARTED`/`COMPLETED`) and connectors
   (`CONNECTOR_CALL_STARTED`/`COMPLETED`).
5. Emit `LLM_CALL_STARTED`, call `ModelProvider.complete()` with the output schema from
   `agent_version.output_schema_id` forced, emit `LLM_CALL_COMPLETED` with the parsed result.
6. Validate the result against the JSON Schema before accepting it — if it doesn't validate, retry
   the model call once with the validation error appended to context; if it fails twice, emit
   `RUN_FAILED` and set `run.status = 'failed'`.
7. On success: `run.output = <result>`, `run.status = 'completed'`, `completed_at = now()`, emit
   `RUN_COMPLETED`.

Every emitted event is a `run_trace` insert with a monotonically increasing `seq_no` — never an
update. `GET /runs/{id}/trace/stream` (SSE) replays existing rows on connect, then polls for new
`seq_no` values (300ms interval is sufficient at this scale; no need for `LISTEN`/`NOTIFY`).

## 9. Evaluation scoring (module: `evaluation`)

1. `POST /agents/{id}/versions/{versionId}/evaluate { evaluationDatasetId }`.
2. For each `evaluation_case` in the dataset, run the full sequence in §8 synchronously
   (reusing the same executor — an evaluation run is just N real runs against known inputs).
3. Score a case as **pass** if the run's `output` deep-equals `expected_output` under a
   caller-supplied comparison strategy — the default strategy is exact structural match on a
   configurable subset of fields (declared alongside the dataset, e.g. "compare only the
   `violations` array, ignore free-text explanation fields"), since exact full-object equality is
   usually too strict for LLM outputs with any prose fields.
4. `score = pass_count / (pass_count + fail_count)`; `status = 'passed'` if `score >= threshold`
   (default `0.9`, configurable per dataset).
5. Insert one `evaluation_run` row summarizing the batch. Individual per-case results are not
   persisted separately in the MVP schema — if you need per-case drill-down, add an
   `evaluation_run_case_result` table (`evaluation_run_id`, `evaluation_case_id`, `passed`,
   `actual_output`) as a straightforward extension; it isn't required for the publish gate itself.

## 10. Versioning rules (apply uniformly to `agent_version`, `workflow_version`, `prompt_version`)

- A new version always gets `version_number = max(existing) + 1` for its parent, starting at 1.
- Only one mutable "draft" (unpublished) version should exist at a time per parent in the UI
  convention, though the schema doesn't hard-enforce this — the API layer should reject creating a
  second draft while one is unpublished, to avoid version sprawl (`409` with a clear message
  pointing at the existing draft's id).
- Publishing never deletes or edits a prior published version — history is always fully
  reconstructable from `agent_version`/`workflow_version`/`prompt_version` rows alone.

## 11. Frontend data flow (see `UI-COMPONENTS.md` for component detail)

`ui/src/lib/api/*` holds one typed client file per resource (`agents.ts`, `runs.ts`, etc.), each a
thin wrapper over `fetch` against `/api/*`. The Playground's trace viewer opens an `EventSource`
against `/api/runs/{id}/trace/stream` and appends events to local state keyed by `seq_no` — no
global state library needed for this; a single `useReducer` in the Playground page is sufficient
at this scale.
