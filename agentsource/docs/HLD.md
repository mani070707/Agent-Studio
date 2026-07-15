# High-Level Design — AgentSource

A generic, self-contained platform for designing, testing, evaluating, and publishing
tool-calling AI agents. This document (with `LLD.md`, `API-ROUTES.md`, `UI-COMPONENTS.md`,
`DB-SCHEMA.sql`, and `BUILD-PLAN.md` alongside it) is written to be a complete, standalone
reference — everything needed to build the platform from scratch is in this folder. No external
codebase is required as a reference.

This is a **domain-agnostic** agent platform: it doesn't assume insurance, finance, healthcare, or
any other vertical. The example agent used throughout these docs (a document-layout checker) is
just one illustration of what can be built on top of it — the platform itself is the product.

---

## 1. Vision

Most "AI agent" demos are a single script that calls an LLM in a loop. AgentSource is the next
step up: a **platform** with a design-time surface (author an agent, its tools, its prompts, its
expected output shape, wire it into a workflow) and a runtime surface (trigger it, watch it execute
step by step, inspect the trace, gate publishing behind an evaluation score). That split — control
plane vs. data plane — is what turns "I called an LLM API" into "I built agent infrastructure."

## 2. Core domain concepts

| Concept | What it is |
|---|---|
| **Agent** | A named, versioned unit of agent behavior. Has a mutable `draft` state and immutable `published` versions. |
| **AgentVersion** | An immutable snapshot: a harness config (tool/skill/MCP allowlists + model settings), a skill (prompt), and an output schema. Created from a draft, frozen on publish. |
| **Skill** | A prompt template plus the instructions for how to use the allowed tools to accomplish a task. |
| **SchemaEntry** | A JSON Schema describing either an input shape or a required output shape. Output schemas are used to force structured LLM responses. |
| **Tool** | A function the agent can call. Two kinds: **platform tools** (built into the runtime, e.g. a document parser) and **MCP tools** (served by an external or self-hosted MCP server over the Model Context Protocol). |
| **Connector** | A way to reach the outside world generically — REST call, message queue publish, or an "LLM task" (a raw model call outside the agent harness, used for simple pipeline steps). |
| **Workflow** | A process definition (steps, branches, triggers) that an agent's execution runs inside. Supports a simple linear model by default; a BPMN engine is an optional upgrade (see §7). |
| **Run** | One execution of a published agent version against one input. Has a status and a final output. |
| **RunTrace** | An ordered, immutable log of every step a run took — tool calls, MCP calls, LLM calls, and their outputs. Streamed live to the UI. |
| **EvaluationDataset / Case / Run** | A golden set of inputs + expected outputs, and the scored result of running an agent version against that set. Gates publishing. |

## 3. Architecture: control plane vs. data plane

**Control plane** (design-time): the UI plus the registry APIs. Where a human authors an agent —
picks its tools, writes its skill/prompt, defines its expected output shape, wires up any MCP
servers or connectors it needs, and runs an evaluation before publishing.

**Data plane** (runtime): the execution engine. On a trigger (HTTP call, file upload, or a workflow
step), it loads a **published** agent version (never a draft — drafts are for design-time testing
only via a "run draft" path used in the Playground), executes its allow-listed tools and MCP calls,
makes the model call with a forced output schema, and emits a trace of everything it did.

The two planes talk to each other exactly once per run: the data plane reads a frozen
`AgentVersion` snapshot; it never mutates control-plane state. This is what makes "publish" mean
something — once published, a version's behavior can't silently change under running traffic.

## 4. Modules

| Module | Owns |
|---|---|
| `agents` | `agent`, `agent_version` — CRUD, versioning, publish gate enforcement |
| `skills` | `skill` — prompt template CRUD |
| `schema-registry` | `schema_entry` — JSON Schema CRUD, used for both tool I/O and agent output |
| `tools` | Platform tool implementations + a registry of which tools exist and their I/O schemas |
| `mcp` | `mcp_server`, `mcp_tool` — register external/self-hosted MCP servers, discover their tools via `tools/list` |
| `connectors` | `connector` — REST / queue / LLM-task connector definitions and execution |
| `prompts` | `prompt`, `prompt_version` — standalone prompt library, separate from skills, for reusable prompt fragments |
| `workflow` | `workflow`, `workflow_version` — process definitions; optional BPMN engine integration |
| `runs` | `run`, `run_trace` — the runtime executor and the SSE trace stream |
| `evaluation` | `evaluation_dataset`, `evaluation_case`, `evaluation_run` — scoring and the publish gate |
| `app` | Spring Boot entrypoint, DB migrations, module wiring |

## 5. Provider abstraction

Every external dependency (the LLM call, an MCP transport, a connector's target system) is defined
as a Java interface with a **mock implementation** that simulates realistic latency and output
shape. This means the whole platform is runnable and demoable with zero external accounts except
one real LLM API key — everything else can run against mocks, and swapping a mock for a real
integration is a config change, not a rewrite. See `LLD.md` §2 for the interface shapes.

## 6. Secrets

No raw credentials are ever stored in a run, a trace, a config blob, or a log line. Every place a
credential is needed, the schema stores a `secretRef` (a name) instead of a value; a small
`SecretResolver` service resolves that name to an actual value at execution time, reading from
(in order) a `secret` table in the database, then an environment variable of the same name. This
lets the whole platform ship with zero secrets checked into git — `.env.example` documents exactly
one required variable (the LLM API key) for a from-scratch run.

## 7. Workflow engine — two supported tiers

- **Tier 1 (default, no extra engine)**: a workflow is just an ordered list of steps, each either
  "run this agent version" or "call this connector." The `runs` module executes steps in order and
  emits the same `run_trace` events either way. This is enough for the vast majority of demos and
  needs nothing beyond Postgres.
- **Tier 2 (optional upgrade)**: swap the Tier-1 step executor for an embedded BPMN engine (e.g.
  Camunda 7, Flowable, or similar) with workflows authored visually and deployed as BPMN XML, and
  agent execution wired as an external task topic. This is a drop-in replacement behind the same
  `WorkflowExecutor` interface — nothing in the `agents`, `runs`, or `evaluation` modules needs to
  change to adopt it.

Building Tier 1 first and treating Tier 2 as a later upgrade avoids taking on a second execution
engine before the core agent-authoring story works end to end.

## 8. Tech stack

| Layer | Choice | Why |
|---|---|---|
| Frontend | Next.js, React, TypeScript | Modern, widely recognized full-stack skill set |
| Backend | Java 17, Spring Boot, multi-module Maven | Enterprise-credible, clean module boundaries |
| Database | PostgreSQL + Flyway migrations | Versioned schema, free-tier friendly |
| Agent protocol | Model Context Protocol (MCP) for tool servers | Current, portable tool-serving standard |
| Live observability | Server-Sent Events | Simple one-directional streaming, no extra infra |
| Workflow (optional) | Embedded BPMN engine | Enterprise workflow orchestration story, opt-in |
| Deployment | Docker Compose | One command, reproducible, no cloud account needed |

## 9. Non-functional requirements

- Entire stack runs via `docker compose up --build` with exactly one required secret.
- Published agent versions are immutable; only drafts can be edited.
- Every run produces an append-only trace; trace rows are never updated, only inserted.
- No agent version can be published without a passing evaluation run against its declared golden
  dataset.
- The platform has no built-in assumption about what an agent is *for* — the domain logic lives
  entirely in a skill's prompt, its tool allowlist, and its output schema, never in platform code.

## 10. What a demo looks like

1. Author an agent: give it a name, write its skill prompt, pick its tools (a platform tool and/or
   an MCP tool), define its output schema.
2. Run it in the Playground against a test input — watch the trace populate live, inspect the
   final structured output.
3. Create an evaluation dataset with a few known-answer cases; run the evaluation; see a pass/fail
   score.
4. Publish the agent version — blocked if the evaluation didn't pass threshold, allowed if it did.
5. Trigger the published version via its API endpoint from outside the platform, exactly as a real
   caller would.

That loop — author, test, evaluate, gate, publish, invoke — is the entire product.
