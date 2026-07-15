# AgentSource

A generic, self-contained platform for designing, testing, evaluating, and publishing tool-calling
AI agents — control plane (author) + data plane (run) + observability (trace) + a publish gate
(evaluation). No vertical/domain assumptions are baked in; the platform is generic, everything
domain-specific lives in a skill's prompt, its tool allowlist, and its output schema.

This folder is a complete, standalone design package — **no other repository is needed** to build
this. Read the docs in this order:

1. [`docs/HLD.md`](docs/HLD.md) — what this is, why it's structured this way, the tech stack
2. [`docs/LLD.md`](docs/LLD.md) — module internals, interfaces, the publish and run sequences
3. [`docs/DB-SCHEMA.sql`](docs/DB-SCHEMA.sql) — the full Postgres schema, ready to run as a Flyway migration
4. [`docs/API-ROUTES.md`](docs/API-ROUTES.md) — every REST endpoint, request/response shapes
5. [`docs/UI-COMPONENTS.md`](docs/UI-COMPONENTS.md) — every screen and reusable component
6. [`docs/BUILD-PLAN.md`](docs/BUILD-PLAN.md) — the milestone order to actually build it (M0–M12,
   plus optional stretch goals)

## What's already in this folder vs. what still needs building

Already here:
- `docker-compose.yml` + `.env.example` — the target deployment shape (`docs/BUILD-PLAN.md` M0)
- `examples/` — a sample harness config, output schema, skill prompt, and an optional Tier-2 BPMN
  workflow, all placeholders showing the *shape* of real content, not a real agent
- `mcp-server-example/` — a minimal working stub implementing the MCP `tools/list`/`tools/call`
  contract from `docs/LLD.md` §4, enough to register against and demo the MCP registry flow

Not yet built (this is the actual implementation work, tracked milestone-by-milestone in
`docs/BUILD-PLAN.md`): `backend/` (all Spring Boot modules) and `ui/` (the Next.js app). Their
target internal structure is fully specified in `docs/LLD.md` §1 and `docs/UI-COMPONENTS.md`.

## Quick start (once backend/ and ui/ exist, per the build plan)

```bash
cp .env.example .env       # leave LLM_API_KEY blank to run entirely on mocks
docker compose up --build
# UI:      http://localhost:3000
# API:     http://localhost:8080
# Postgres: localhost:5433
```

## Using this with an LLM to build the project

Hand `docs/BUILD-PLAN.md` to your coding agent first — it references exactly which other doc
section is needed per milestone. Don't paste the whole doc set into every prompt; each milestone
only needs its own slice, per the "How to use this with an LLM pair-programmer" note at the bottom
of `docs/BUILD-PLAN.md`.
