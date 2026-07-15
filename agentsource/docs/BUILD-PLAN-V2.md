# Build Plan V2 — Agent Studio (this implementation)

This supersedes `BUILD-PLAN.md`/`HLD.md`/`LLD.md` for how this repo is actually being built. Those
documents remain the original reference design (Spring Boot backend, Docker Compose, single-tenant)
and are still useful for the *concepts* (control plane vs. data plane, harness config, publish gate,
run trace). This doc captures the deviations and the concrete chunked build plan for the real stack
in use.

## Why this deviates from the original design

| Original design | This build | Why |
|---|---|---|
| Spring Boot, multi-module Maven | Python (FastAPI) | Faster to stand up and deploy solo, same portfolio value |
| Docker Compose, self-hosted Postgres | Supabase (Postgres + Auth + Storage), free tier | No AWS/paid infra allowed; Supabase bundles DB+Auth+Storage in one free project |
| Single-tenant demo | Real multi-user, public hosting | Actual use case is "anyone can come make their own agent and use it" |
| Shared/no LLM key | BYOK per user | Public multi-user instance can't be cost-exposed to one owner's key |
| One `skill.body` prompt | `system_prompt` + `user_prompt_template` (separate, versioned) | Confirmed against the reference agent-builder UI screenshots — system and user prompts are bound separately, each its own versioned entity |
| `toolAllowlist`/`mcpToolAllowlist`/`connectorAllowlist` only | Same, plus `skillAllowlist` and an `agent_trigger` table (manual/api/schedule) | Reference UI shows "Allowed Skills" as its own multi-select, and triggers as a repeatable list, not a single invoke path |
| Evaluation always gates publish | Evaluation is an optional per-agent toggle (`evaluation_gate_enabled`) | Reference UI shows an explicit disable option — most agents won't need a formal eval dataset on day one |
| No content/document store | `content_item` module (per-agent file upload + extracted text + `search_documents` tool) | Needed for the document-validator and resume-based examples |
| Kafka output | Dropped | Out of scope |

## Architecture

```
Next.js (Vercel, free)  ──JWT bearer──▶  FastAPI (Render/Fly, free)
        │  signup/login (direct)                │
        ▼                                        ▼
   Supabase (free tier): Auth (JWT) + Postgres (all tables) + Storage (uploads)
                                                  │
                                                  ▼
                        External: user's own LLM key (BYOK) · registered MCP servers ·
                        registered REST connectors · free no-key web search/fetch
```

## Full DB schema

```
agent(id, user_id, name, agent_type[task|chat|workflow], domain, owner, tags[], description,
      status[draft|active], evaluation_gate_enabled, created_at, updated_at)
agent_version(id, agent_id, version_number, harness_config jsonb, skill_id, input_schema_id,
      output_schema_id, tool_allowlist[], mcp_tool_allowlist[], connector_allowlist[],
      skill_allowlist[], is_published, published_at, created_at)
agent_trigger(id, agent_id, name, type[manual|api|schedule], auth_type, config jsonb, enabled)
skill(id, user_id, name, system_prompt, user_prompt_template, version, is_published)
schema_entry(id, user_id, name, kind[input|output], json_schema jsonb, version)
platform_tool(name pk, description, input_schema, output_schema)      -- seeded by backend code
mcp_server(id, user_id, name, url, secret_ref)
mcp_tool(id, mcp_server_id, tool_name, input_schema, output_schema)
connector(id, user_id, name, base_url, auth_secret_ref, request_template jsonb)
content_item(id, user_id, agent_id, filename, storage_path, extracted_text)
user_secret(id, user_id, name, encrypted_value)
run(id, agent_version_id, user_id, trigger_id, input jsonb, output jsonb, status, started_at, completed_at)
run_step(id, run_id, step_num, type, detail jsonb)
evaluation_dataset(id, agent_id, name, threshold default 0.9)
evaluation_case(id, dataset_id, input jsonb, expected_output jsonb, compare_fields[])
evaluation_run(id, agent_version_id, dataset_id, score, status)
```

`harness_config` shape (mirrors the reference UI's Harness step):
```json
{
  "runtimeModel": {"provider": "anthropic", "modelId": "claude-sonnet-5", "temperature": 0, "maxTokens": 16000, "timeoutMs": 300000, "apiKeySecretRef": "..."},
  "promptGuardrails": {"role": "...", "goal": "...", "guardrailProfile": "standard", "contextMode": "minimal"},
  "memory": {"vectorMemoryEnabled": false, "graphMemoryEnabled": false, "episodicMemoryEnabled": false}
}
```

## Chunked build plan

Each chunk is independently demoable. **After every chunk: stop and review before starting the
next one** — see Review Plan below. Do not stack unreviewed chunks.

| # | Chunk | Depends on | Definition of done |
|---|---|---|---|
| M0 | Repo scaffold: `web/` (Next.js) + `api/` (FastAPI) skeletons, `.env.example` for both, root README | — | Both run locally (`npm run dev`, `uvicorn`); `api/health` returns 200 |
| M1 | Supabase project created (manual, by you) + full DB schema applied as a migration | M0 | All tables exist in Supabase Postgres |
| M2 | Auth end-to-end | M1 | Signup/login via Supabase Auth in Next.js issues a JWT; FastAPI middleware verifies it via Supabase JWKS and extracts `user_id` on a protected test route |
| M3 | Secrets module (BYOK) | M2 | User can save an encrypted LLM key via UI; value never returned by any GET |
| M4 | Skills + Schemas modules | M2 | CRUD for system/user prompt pairs and JSON schemas, via UI forms |
| M5 | Built-in platform tools | M2 | `calculator`, `url_fetch`, `web_search` (DuckDuckGo IA) implemented; `/tools/platform` lists them |
| M6 | Content store | M2 | Upload a file → Supabase Storage, text extracted, `search_documents` tool works against it |
| M7 | Agents module + Basics/Harness wizard UI | M3, M4, M5 | Create a draft agent version with runtime model + skill + schemas + tool allowlist |
| M8 | Runs executor | M7 | Trigger a run: builds system+user message, calls user's LLM key, dispatches tool calls, validates output against schema, logs `run_step` rows |
| M9 | Playground UI (trace viewer) | M8 | Run a draft version from the UI, watch steps populate, see final structured output |
| M10 | Triggers + publish/versioning + Review step + agent detail page tabs | M9 | Manual + API triggers work; publish flips `is_published`; edits require a new draft |
| M11 | MCP module | M7 | Register an MCP server URL → tools sync into `mcp_tool` → allow-listed tools callable at run time |
| M12 | Connectors module | M7 | Define a REST connector in UI → test + execute it |
| M13 | Evaluation module (per-agent toggle) | M10 | Dataset/case CRUD; when `evaluation_gate_enabled`, publish blocked below threshold |
| M14 | Scheduling (`agent_trigger type=schedule`) + free external cron | M10 | AI-news-digest agent runs daily unattended, results land in Runs history |
| M15 | Polish: README + 3 example agents pre-built + demo script | M11, M12, M14 | A stranger can sign up, see 3 working example agents, and build a 4th from scratch |

Stretch (post-M15): Memory module — episodic (Postgres, no new infra) any time after M8; vector
(Qdrant free tier) and graph (Neo4j Aura free tier) as their own later phase.

## Review plan (after every chunk, before starting the next)

1. **Functional check against the chunk's Definition of Done** — run the exact check listed in the
   table above (curl a route, click through the UI flow, etc.). Not "it compiles" — the stated DoD.
2. **Code review pass** — run `/code-review` (or equivalent) over the chunk's diff before it's
   considered done; fix or explicitly accept findings.
3. **Regression spot-check** — re-run the previous chunk's DoD check too, to catch anything the new
   chunk broke.
4. **Explicit sign-off** — you confirm the chunk is good before the next one starts. No chunk begins
   while the prior one's review is open.
5. **Log it** — mark the chunk done in this doc (append a `✅ done <date>` note next to its row) so
   the build history stays visible in the repo, not just in chat.

## Example-agent → chunk mapping

- **Document validator**: M5 + M6 + M7 + M8 + M9
- **Resume-based job application assistant**: adds M12 (optional auto-submit connector)
- **Recurring AI news digest**: adds M14 (scheduling)
