# Build Plan — AgentSource

A milestone-ordered plan for building the platform described in `HLD.md`/`LLD.md`. Each milestone
is independently runnable and demoable — never leave the app broken between milestones. Backend
milestones (M0–M9) are verifiable with curl/Postman alone, before any UI work starts, which makes
this friendly to an incremental, LLM-assisted build: each milestone is a self-contained prompt.

| # | Milestone | Depends on | Definition of done |
|---|---|---|---|
| M0 | Repo scaffold: `docker-compose.yml` (postgres, backend, ui, mcp-server-example), `.env.example` with one variable (`LLM_API_KEY`) | — | `docker compose up` starts all four containers; backend `/actuator/health` (or equivalent) returns `200` |
| M1 | Full schema from `DB-SCHEMA.sql` as a Flyway migration in `backend/app` | M0 | Migration applies cleanly to an empty DB; all tables + the `agent_version_publish_status` view exist |
| M2 | `common` module: `SecretResolver`, `ModelProvider`/`McpClient`/`ConnectorExecutor` interfaces + **mock** implementations | M1 | A throwaway test calls each mock and gets a plausible fake response |
| M3 | CRUD APIs: `skills`, `schema-registry`, `prompts` modules | M2 | Can create/list/update a skill, a schema, a prompt via curl |
| M4 | `tools` module: `PlatformToolRegistry` + one example platform tool implementing `PlatformTool` | M3 | Startup log shows the tool registered; `GET /tools/platform` lists it |
| M5 | `mcp-server-example` (standalone Node service) + `mcp` module registering it and syncing its tools | M3 | `POST /mcp-servers` against the example server populates `mcp_tool` rows matching what `tools/list` returns |
| M6 | `connectors` module + one REST-type connector example | M3 | `POST /connectors/{id}/test` against a public test endpoint (e.g. httpbin) returns its response |
| M7 | `agents` module: agent + draft version CRUD, harness config validation against allowlisted tools/mcp-tools/connectors | M4, M5, M6 | Creating a version with a tool name not in the registry is rejected with a clear `400` |
| M8 | `runs` module: executor (§8 in `LLD.md`), SSE trace stream, wired to the **mock** `ModelProvider` | M7 | Triggering a run against a draft-testable path produces a full `run_trace` sequence and a `run.output`; `GET /runs/{id}/trace/stream` shows events arriving live |
| M9 | `evaluation` module: dataset/case CRUD, evaluate endpoint, publish-gate check on `agents` publish | M8 | Evaluating with a dataset where every expected output is achievable scores `1.0`; publish is rejected below threshold and allowed above it |
| M10 | Swap `ModelProvider` to a **live** implementation (real LLM API) behind a Spring profile | M9 | Setting `LLM_API_KEY` and the `live` profile produces real (non-canned) model output through the same executor, no code changes elsewhere |
| M11 | UI build order per `UI-COMPONENTS.md` §7: registries → agent builder → playground/trace viewer → evaluation/publish → dashboard/runs/workflows | M9 (can start against mocks before M10) | A reviewer can complete the full demo loop from `HLD.md` §10 without touching an API client directly |
| M12 | README with setup steps + screenshots/GIF of the Playground trace view | M11 | A stranger can clone, set one env var, run one command, and reach a working demo in under five minutes |

## Optional stretch milestones

| # | Milestone | Notes |
|---|---|---|
| S1 | Tier 2 workflow upgrade: embed a BPMN engine, `bpmn-js` canvas in `WorkflowsPage`, external-task-style dispatch to the same `runs` executor | Only take this on after M12 — it's a horizontal-scope addition, not required for the core story |
| S2 | Per-case evaluation drill-down (`evaluation_run_case_result` table, per LLD §9 note) | Nice for debugging why a score is low, not required for the gate itself |
| S3 | Auth (single Spring filter, per `API-ROUTES.md` "Auth" note) | Only relevant if deploying somewhere multi-user |

## How to use this with an LLM pair-programmer

Feed one milestone at a time, in order, along with the relevant section(s) of `LLD.md` and
`DB-SCHEMA.sql`. Don't feed the whole doc set for every milestone — M4 only needs `LLD.md` §5 and
the `platform_tool` table, for example. Verify each milestone's definition-of-done before moving to
the next; a milestone that "mostly works" compounds into a much harder debugging session three
milestones later.
