-- Agent Studio — initial schema. Run this once in the Supabase SQL editor (or via psql
-- against DATABASE_URL) against a fresh project. Matches api/app/db/models.py exactly —
-- if you change a model, add a new numbered migration file, never edit this one in place.

create extension if not exists pgcrypto;

-- ============================================================================
-- Skills, schemas, secrets, platform tools
-- ============================================================================

create table skill (
  id                    text primary key,
  user_id               uuid not null references auth.users(id) on delete cascade,
  name                  text not null,
  system_prompt         text not null,
  user_prompt_template  text not null,
  version               int not null default 1,
  is_published          boolean not null default false
);
create index idx_skill_user_id on skill(user_id);

create table schema_entry (
  id           text primary key,
  user_id      uuid not null references auth.users(id) on delete cascade,
  name         text not null,
  kind         text not null check (kind in ('input', 'output')),
  json_schema  jsonb not null,
  version      text not null default '1.0.0'
);
create index idx_schema_entry_user_id on schema_entry(user_id);

create table user_secret (
  id               text primary key,
  user_id          uuid not null references auth.users(id) on delete cascade,
  name             text not null,
  encrypted_value  text not null,
  unique (user_id, name)
);
create index idx_user_secret_user_id on user_secret(user_id);

create table platform_tool (
  name            text primary key,
  description     text not null,
  input_schema    jsonb not null,
  output_schema   jsonb not null
);

-- ============================================================================
-- MCP servers/tools, connectors, content store
-- ============================================================================

create table mcp_server (
  id          text primary key,
  user_id     uuid not null references auth.users(id) on delete cascade,
  name        text not null,
  url         text not null,
  secret_ref  text
);
create index idx_mcp_server_user_id on mcp_server(user_id);

create table mcp_tool (
  id              text primary key,
  mcp_server_id   text not null references mcp_server(id) on delete cascade,
  tool_name       text not null,
  input_schema    jsonb not null,
  output_schema   jsonb not null
);
create index idx_mcp_tool_server_id on mcp_tool(mcp_server_id);

create table connector (
  id                 text primary key,
  user_id            uuid not null references auth.users(id) on delete cascade,
  name               text not null,
  base_url           text not null,
  auth_secret_ref    text,
  request_template   jsonb not null
);
create index idx_connector_user_id on connector(user_id);

create table content_item (
  id               text primary key,
  user_id          uuid not null references auth.users(id) on delete cascade,
  agent_id         text not null,
  filename         text not null,
  storage_path     text not null,
  extracted_text   text not null default ''
);
create index idx_content_item_user_id on content_item(user_id);
create index idx_content_item_agent_id on content_item(agent_id);

-- ============================================================================
-- Agents, versions, triggers
-- ============================================================================

create table agent (
  id                        text primary key,
  user_id                   uuid not null references auth.users(id) on delete cascade,
  name                      text not null,
  agent_type                text not null default 'task' check (agent_type in ('task', 'chat', 'workflow')),
  domain                    text not null default '',
  owner                     text not null default '',
  tags                      jsonb not null default '[]',
  description               text not null default '',
  status                    text not null default 'draft' check (status in ('draft', 'active')),
  evaluation_gate_enabled   boolean not null default false
);
create index idx_agent_user_id on agent(user_id);

create table agent_version (
  id                    text primary key,
  agent_id              text not null references agent(id) on delete cascade,
  version_number        int not null,
  harness_config        jsonb not null,
  skill_id              text not null references skill(id),
  input_schema_id       text references schema_entry(id),
  output_schema_id      text not null references schema_entry(id),
  tool_allowlist        jsonb not null default '[]',
  mcp_tool_allowlist    jsonb not null default '[]',
  connector_allowlist   jsonb not null default '[]',
  skill_allowlist       jsonb not null default '[]',
  is_published          boolean not null default false,
  published_at          text,
  unique (agent_id, version_number)
);
create index idx_agent_version_agent_id on agent_version(agent_id);

create table agent_trigger (
  id          text primary key,
  agent_id    text not null references agent(id) on delete cascade,
  name        text not null,
  type        text not null check (type in ('manual', 'api', 'schedule')),
  auth_type   text not null default '',
  config      jsonb not null default '{}',
  enabled     boolean not null default true
);
create index idx_agent_trigger_agent_id on agent_trigger(agent_id);

-- ============================================================================
-- Runs, run trace
-- ============================================================================

create table run (
  id                  text primary key,
  agent_version_id    text not null references agent_version(id),
  user_id             uuid not null references auth.users(id) on delete cascade,
  trigger_id          text references agent_trigger(id),
  input               jsonb not null,
  output              jsonb,
  status              text not null default 'pending' check (status in ('pending', 'running', 'completed', 'failed')),
  started_at          text,
  completed_at        text
);
create index idx_run_user_id on run(user_id);
create index idx_run_agent_version_id on run(agent_version_id);

create table run_step (
  id        text primary key,
  run_id    text not null references run(id) on delete cascade,
  step_num  int not null,
  type      text not null,
  detail    jsonb not null
);
create index idx_run_step_run_id on run_step(run_id);

-- ============================================================================
-- Evaluation
-- ============================================================================

create table evaluation_dataset (
  id          text primary key,
  agent_id    text not null references agent(id) on delete cascade,
  name        text not null,
  threshold   float not null default 0.9
);
create index idx_evaluation_dataset_agent_id on evaluation_dataset(agent_id);

create table evaluation_case (
  id                text primary key,
  dataset_id        text not null references evaluation_dataset(id) on delete cascade,
  input             jsonb not null,
  expected_output   jsonb not null,
  compare_fields    jsonb not null default '[]'
);
create index idx_evaluation_case_dataset_id on evaluation_case(dataset_id);

create table evaluation_run (
  id                  text primary key,
  agent_version_id    text not null references agent_version(id),
  dataset_id          text not null references evaluation_dataset(id),
  score               float not null default 0.0,
  status              text not null default 'pending' check (status in ('pending', 'passed', 'failed'))
);
create index idx_evaluation_run_agent_version_id on evaluation_run(agent_version_id);

-- ============================================================================
-- Row Level Security — defense in depth. The FastAPI backend connects with a direct
-- Postgres role and enforces tenant isolation in application code (every query filters by
-- user_id); these policies matter if these tables are ever queried directly through
-- Supabase's PostgREST layer with a user's own JWT instead of only through the API.
-- ============================================================================

alter table skill enable row level security;
alter table schema_entry enable row level security;
alter table user_secret enable row level security;
alter table mcp_server enable row level security;
alter table connector enable row level security;
alter table content_item enable row level security;
alter table agent enable row level security;
alter table run enable row level security;

create policy "owner_only" on skill using (auth.uid() = user_id);
create policy "owner_only" on schema_entry using (auth.uid() = user_id);
create policy "owner_only" on user_secret using (auth.uid() = user_id);
create policy "owner_only" on mcp_server using (auth.uid() = user_id);
create policy "owner_only" on connector using (auth.uid() = user_id);
create policy "owner_only" on content_item using (auth.uid() = user_id);
create policy "owner_only" on agent using (auth.uid() = user_id);
create policy "owner_only" on run using (auth.uid() = user_id);

alter table mcp_tool enable row level security;
create policy "owner_only" on mcp_tool using (
  exists (select 1 from mcp_server where mcp_server.id = mcp_tool.mcp_server_id and mcp_server.user_id = auth.uid())
);

alter table agent_version enable row level security;
create policy "owner_only" on agent_version using (
  exists (select 1 from agent where agent.id = agent_version.agent_id and agent.user_id = auth.uid())
);

alter table agent_trigger enable row level security;
create policy "owner_only" on agent_trigger using (
  exists (select 1 from agent where agent.id = agent_trigger.agent_id and agent.user_id = auth.uid())
);

alter table run_step enable row level security;
create policy "owner_only" on run_step using (
  exists (select 1 from run where run.id = run_step.run_id and run.user_id = auth.uid())
);

alter table evaluation_dataset enable row level security;
create policy "owner_only" on evaluation_dataset using (
  exists (select 1 from agent where agent.id = evaluation_dataset.agent_id and agent.user_id = auth.uid())
);

alter table evaluation_case enable row level security;
create policy "owner_only" on evaluation_case using (
  exists (
    select 1 from evaluation_dataset
    join agent on agent.id = evaluation_dataset.agent_id
    where evaluation_dataset.id = evaluation_case.dataset_id and agent.user_id = auth.uid()
  )
);

alter table evaluation_run enable row level security;
create policy "owner_only" on evaluation_run using (
  exists (
    select 1 from agent_version
    join agent on agent.id = agent_version.agent_id
    where agent_version.id = evaluation_run.agent_version_id and agent.user_id = auth.uid()
  )
);

-- platform_tool has no user_id — it's a global, backend-seeded registry, readable by anyone
-- authenticated; no RLS needed since it holds no per-user data.

-- ============================================================================
-- Storage bucket for the content store (per-agent file uploads)
-- ============================================================================

insert into storage.buckets (id, name, public)
values ('agent-studio-content', 'agent-studio-content', false)
on conflict (id) do nothing;

-- Files are stored at "<user_id>/<agent_id>/<uuid>-<filename>" (see api/app/routers/content.py) —
-- this policy lets a user only touch objects under their own user_id prefix, mirroring the
-- table-level RLS policies above. Again: the FastAPI backend uses the service role key for
-- storage access and enforces this in app code too; this is the defense-in-depth layer.
create policy "owner_prefix_only" on storage.objects for all using (
  bucket_id = 'agent-studio-content' and (storage.foldername(name))[1] = auth.uid()::text
);
