# Agent Studio

Agent Studio is a multi-tenant platform for building, testing, evaluating and publishing
tool-calling AI agents. The product uses one Python backend and preserves tenant-owned model keys,
structured prompts, MCP tools, connectors, content, traces and evaluation data.

## Architecture

```text
Next.js :3000 ──> FastAPI :8000 ──> Supabase PostgreSQL
                                  ├── Supabase Auth
                                  └── Supabase Storage
```

- `web/` — Next.js App Router frontend.
- `api/` — Python 3.12 FastAPI modular monolith.
- `architecture/python-fastapi/` — current HLD, LLD, deployment and module guidance.
- `LEARNING-ROADMAP.md` — learn-by-building AI engineering sequence.

## Local setup

```bash
cp api/.env.example api/.env
cp web/.env.example web/.env.local

cd api
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

In another terminal:

```bash
cd web
npm ci
npm run dev
```

Existing databases that already contain migrations `001` and `002` must be registered once with
`alembic stamp 0001_existing_schema`; do not run the baseline upgrade over an existing schema.

Alternatively, run both services with `docker compose up --build`.

## Verification

```bash
cd api
python -m unittest discover -s tests -v
python scripts/export_openapi.py

cd ../web
npm run build
```

## Security invariants

- Every tenant-owned query includes the authenticated Supabase user ID.
- Production validates JWT signature, issuer, audience, expiry and subject.
- Local auth bypass is rejected when `ENVIRONMENT=production`.
- API keys remain Fernet encrypted and are never returned or logged.
- Built-in tools are a code-owned catalog; application startup performs no database seeding.
- Database changes are made only through Alembic.
