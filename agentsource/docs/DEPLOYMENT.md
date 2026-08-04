# Deployment — free tier only, no AWS

Three services: Supabase (data+auth+storage), Render or Fly.io (API), Vercel (web). All free tier.

## 1. Supabase (do this first)

1. Create a project at supabase.com.
2. SQL editor → paste and run `api/migrations/001_init.sql` in full.
3. Project Settings → API: copy the **Project URL**, **anon public key**, **service_role key**.
4. Project Settings → Database: copy the connection string (use the **Session pooler** URI —
   the free tier's direct connection has a low connection cap, the pooler handles bursty
   serverless-style traffic from Render/Fly better).
5. Note the JWKS URL: `https://<project-ref>.supabase.co/auth/v1/.well-known/jwks.json`.
6. Auth → URL Configuration: add your deployed frontend's URL (from step 3 below) as a
   redirect URL once you have it, so email confirmation links work.

## 2. API — Render (or Fly.io)

**Render:**
1. New → Web Service → connect this repo, root directory `api/`.
2. Build command: `pip install -r requirements.txt`
3. Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
4. Environment variables: all of `api/.env.example`'s keys, filled with your real Supabase
   values from step 1, plus a generated `SECRET_ENCRYPTION_KEY` and `INTERNAL_CRON_SECRET`
   (`python -c "import secrets; print(secrets.token_hex(32))"` for either).
5. Set `CORS_ALLOW_ORIGINS` to your Vercel URL once you have it (step 3) — comma-separate if you
   need both the Vercel URL and `http://localhost:3000` for local dev against the deployed API.
6. Deploy. Confirm `https://<your-render-url>/health` returns `{"status": "ok"}`.

Free-tier note: Render's free web services spin down after 15 minutes of inactivity and take
~30s to cold-start on the next request — acceptable for a portfolio demo, not for a low-latency
SLA.

**Fly.io** is an equally valid free-tier alternative if you prefer `fly.toml`-based deploys —
same env vars, same start command.

## 3. Web — Vercel

1. New Project → import this repo, root directory `web/`.
2. Framework preset: Next.js (auto-detected).
3. Environment variables:
   - `NEXT_PUBLIC_SUPABASE_URL` — from step 1
   - `NEXT_PUBLIC_SUPABASE_ANON_KEY` — from step 1
   - `NEXT_PUBLIC_API_BASE_URL` — your Render/Fly URL from step 2
4. Deploy. Visit the Vercel URL, sign up, confirm email, log in.
5. Go back to Render (step 2.5) and Supabase Auth redirect URLs (step 1.6) and set them to this
   real Vercel URL — this is a chicken-and-egg step, expect one round trip between the three
   dashboards on first deploy.

## 4. Scheduling — free external cron

No process runs continuously to fire `schedule`-type triggers; `POST /internal/run-due-schedules`
needs to be hit periodically. Two free options:

**GitHub Actions** (recommended — no extra account):
```yaml
# .github/workflows/run-schedules.yml
name: run-due-schedules
on:
  schedule:
    - cron: "*/15 * * * *"   # every 15 minutes
jobs:
  trigger:
    runs-on: ubuntu-latest
    steps:
      - run: |
          curl -X POST "$API_URL/internal/run-due-schedules" \
            -H "X-Internal-Cron-Secret: $CRON_SECRET"
        env:
          API_URL: ${{ secrets.API_URL }}
          CRON_SECRET: ${{ secrets.INTERNAL_CRON_SECRET }}
```
Add `API_URL` and `INTERNAL_CRON_SECRET` as repo secrets (Settings → Secrets and variables →
Actions) matching what you set on Render/Fly.

**Vercel Cron Jobs** (if you'd rather keep it inside Vercel): add a `vercel.json` with a `crons`
entry pointing at a small Next.js API route that proxies the same POST — only needed if you'd
rather not use GitHub Actions.

## Verifying the full loop after deploy

1. Sign up on the Vercel URL, confirm email, log in.
2. Secrets → add your real `ANTHROPIC_API_KEY` (or `OPENAI_API_KEY`).
3. Skills → create one system+user prompt pair. Schemas → create an output schema.
4. Agents → New agent → Harness (pick the skill/schema/model, tool allowlist) → Trigger →
   Evaluation (leave disabled) → Review → Publish.
5. Playground → run it with a sample input → confirm the trace and output render.
