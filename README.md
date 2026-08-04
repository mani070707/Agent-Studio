# Agent Studio

A publicly hosted, multi-user platform for authoring, testing, evaluating, and running
tool-calling AI agents. Anyone can sign up, build their own agent — a system/user prompt pair,
an output schema, a set of tools (built-in, MCP, or REST connectors), optional document context —
test it in the Playground, publish it, and invoke it, all against their **own** LLM API key
(BYOK). No AWS, no paid infra: the whole stack runs on free tiers.

## Architecture

```
Next.js (Vercel, free)  ──JWT bearer──▶  FastAPI (Render/Fly, free)
        │  signup/login (direct)                │
        ▼                                        ▼
   Supabase (free tier): Auth (JWT) + Postgres (all tables) + Storage (uploads)
                                                  │
                                                  ▼
                        External: user's own LLM key (Anthropic/OpenAI, BYOK) ·
                        registered MCP servers · registered REST connectors ·
                        free no-key web search/fetch (DuckDuckGo Instant Answer)
```

- **Frontend** (`web/`): Next.js (App Router), talks to Supabase directly for auth, and to the
  FastAPI backend (bearer JWT) for everything else.
- **Backend** (`api/`): FastAPI. Owns all agent/skill/tool/MCP/connector/content/run logic,
  verifies every request's Supabase JWT against the project's JWKS, and never exposes a
  credential (LLM key, MCP server secret, connector auth) to the browser.
- **Data** (Supabase, one free project): Postgres (all tables, RLS enabled as defense-in-depth),
  Auth (issues the JWTs the frontend forwards), Storage (per-agent uploaded documents).
- **Scheduling**: no in-process scheduler. A free external cron (GitHub Actions scheduled
  workflow, or Vercel Cron Jobs) hits `POST /internal/run-due-schedules` on a timer.

See [`agentsource/docs/BUILD-PLAN-V2.md`](agentsource/docs/BUILD-PLAN-V2.md) for the full schema,
module list, and how this deviates from the original `agentsource/` reference design (which
specified Spring Boot + Docker Compose + single-tenant — this build is Next.js + FastAPI +
Supabase + multi-tenant, for the reasons documented there).

## Project structure

```
agentsource/              Original reference design docs (concepts, not the literal stack used)
  docs/BUILD-PLAN-V2.md    This build's actual architecture, schema, and deviations
  docs/API-ROUTES-V2.md    Every implemented API route
  docs/DEPLOYMENT.md       Free-tier deployment steps (Vercel + Render/Fly + Supabase)

api/                       FastAPI backend
  app/
    core/                  config, auth (Supabase JWT verification), secrets, SSRF guard
    db/                    SQLAlchemy models, session, shared CRUD helper
    llm/                   Anthropic + OpenAI session wrappers (BYOK)
    tools/                 Built-in platform tools (calculator, url_fetch, web_search, search_documents)
    mcp_client/            MCP client (tools/list, tools/call) over streamable HTTP
    connectors/            Generic REST connector executor
    content/               Document text extraction (PDF/txt)
    storage/               Supabase Storage upload/delete
    agents/                Harness-selection validation
    runs/                  The agent tool-calling loop executor
    routers/               One file per resource — this is the actual API surface
  migrations/001_init.sql  Full Postgres schema + RLS policies — run once against Supabase
  requirements.txt
  .env.example

web/                       Next.js frontend
  app/
    login/, signup/        Auth pages
    (app)/                 Everything behind AuthGuard: agents, skills, schemas, secrets,
                            mcp-servers, connectors, content, runs
  lib/                     Supabase client, typed API fetch wrapper, shared TS types
  components/               AuthGuard, Nav
  package.json
  .env.example
```

## Quick Start

1. **Create a Supabase project** (free tier, supabase.com) — this is an account-creation step
   you do yourself. Note the Project URL, anon key, service role key, and DB connection string
   (Project Settings → API and → Database).
2. **Apply the schema**: open the Supabase SQL editor and run `api/migrations/001_init.sql`
   in full. This creates every table, enables RLS, and creates the `agent-studio-content`
   storage bucket.
3. **Configure the backend**:
   ```bash
   cd api
   cp .env.example .env   # fill in SUPABASE_URL, SUPABASE_JWKS_URL, SUPABASE_SERVICE_ROLE_KEY,
                          # DATABASE_URL, SECRET_ENCRYPTION_KEY, INTERNAL_CRON_SECRET
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   uvicorn app.main:app --reload --port 8000
   ```
   `SUPABASE_JWKS_URL` is `https://<project-ref>.supabase.co/auth/v1/.well-known/jwks.json`.
   Generate `SECRET_ENCRYPTION_KEY` with:
   `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
4. **Configure the frontend**:
   ```bash
   cd web
   cp .env.example .env.local   # fill in NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY
   npm install
   npm run dev                 # http://localhost:3000
   ```
5. **Sign up** at `http://localhost:3000/signup`, confirm your email (Supabase sends this), log
   in, go to **Secrets** and add your own `ANTHROPIC_API_KEY` (or `OPENAI_API_KEY`), then build
   your first agent under **Agents → New agent**.

## Deployment

See [`agentsource/docs/DEPLOYMENT.md`](agentsource/docs/DEPLOYMENT.md) for deploying `web/` to
Vercel and `api/` to Render or Fly.io, both on free tiers.

## API reference

See [`agentsource/docs/API-ROUTES-V2.md`](agentsource/docs/API-ROUTES-V2.md).

## Security notes

- Every credential (LLM keys, MCP server secrets, connector auth) is stored as an encrypted
  `user_secret` row and resolved server-side only — never sent to or stored in the browser.
- All outbound fetches the backend makes on a user's behalf (`url_fetch` tool, connector calls)
  are checked against an SSRF guard that blocks private/loopback/link-local/reserved IP ranges,
  including on every redirect hop.
- The FastAPI backend verifies every request's JWT signature against Supabase's live JWKS
  (cached 1h) — there is no mock or bypass auth path in this build.
- RLS is enabled on every table as defense-in-depth; the backend's own Postgres connection uses
  a role that bypasses RLS and enforces tenant isolation in application code (every query filters
  by `user_id`) as the primary boundary.

## Known limitations (by design, given free-tier/solo-build constraints)

- **Runs execute synchronously** — the HTTP request that triggers a run blocks until it
  completes (no queue/worker infra is provisioned). Fine for tool-calling loops that finish in
  seconds; not suited to very long-running agents.
- **No live streaming trace** — the Playground shows the full step list after a run completes,
  not a live SSE feed.
- **No Tier-2 BPMN workflow engine** — `agent_type: "workflow"` is accepted by the schema but has
  no executor; only `task` (single bounded run) is implemented.
- **Vector/graph memory** are schema fields (`memory.vector_memory_enabled` etc.) that are not
  wired to Qdrant/Neo4j — flagged in the harness as a future phase, not silently ignored.
