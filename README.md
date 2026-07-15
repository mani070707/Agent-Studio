# Agent Studio

A publicly hosted, multi-user platform for authoring, testing, evaluating, and running tool-calling
AI agents — anyone can sign up, build their own agent, and run it against their own LLM key (BYOK).

## Repo layout

- `agentsource/` — the original reference design package (Spring Boot/Docker Compose architecture,
  domain concepts, harness config shape). Kept as the conceptual reference; **not** the literal
  stack used here. See `agentsource/docs/BUILD-PLAN-V2.md` for what actually deviates and why.
- `web/` — Next.js frontend (deployed to Vercel, free tier).
- `api/` — FastAPI backend (deployed to Render/Fly, free tier). Owns all agent/skill/tool/MCP/run
  logic and BYOK secret handling.
- Data + Auth + file storage: Supabase (free tier) — one project for Postgres, Auth, and Storage.

## Build plan

Build is chunked (M0–M15); see `agentsource/docs/BUILD-PLAN-V2.md` for the full milestone table,
the DB schema, and the review process followed after each chunk.

## Local dev (M0)

```bash
# frontend
cd web && cp .env.example .env.local && npm install && npm run dev   # http://localhost:3000

# backend
cd api && cp .env.example .env
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000                            # http://localhost:8000/health
```
