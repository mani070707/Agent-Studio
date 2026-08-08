"""Add durable LangGraph workflow execution metadata.

Revision ID: 0008_langgraph_workflows
Revises: 0007_langchain_runtime
"""
from alembic import op

revision = "0008_langgraph_workflows"
down_revision = "0007_langchain_runtime"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
      create table workflow_execution(
        run_id text primary key references run(id) on delete cascade,
        user_id uuid not null references auth.users(id) on delete cascade,
        thread_id text not null unique, graph_version text not null default 'research_v1',
        current_node text not null default 'prepare', status text not null default 'queued',
        pending_interrupt jsonb not null default '{}'::jsonb, resumable boolean not null default false,
        checkpoint_expires_at timestamptz not null, created_at timestamptz not null default now(),
        updated_at timestamptz not null default now(), unique(run_id,user_id));
      create table workflow_job(
        run_id text primary key, user_id uuid not null references auth.users(id) on delete cascade,
        status text not null default 'queued', attempt_count integer not null default 0,
        max_attempts integer not null default 3, available_at timestamptz not null default now(),
        lease_owner text, lease_until timestamptz, last_error_code text, last_error_message text,
        created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
        foreign key(run_id,user_id) references workflow_execution(run_id,user_id) on delete cascade);
      create index idx_workflow_job_claim on workflow_job(status,available_at,created_at);
      create table workflow_approval(
        id text primary key, run_id text not null, user_id uuid not null references auth.users(id) on delete cascade,
        tool_name text not null, tool_type text not null, arguments jsonb not null default '{}'::jsonb,
        arguments_hash text not null, status text not null default 'pending', reason text not null default '',
        decided_by uuid, created_at timestamptz not null default now(), decided_at timestamptz,
        expires_at timestamptz not null, foreign key(run_id,user_id) references workflow_execution(run_id,user_id) on delete cascade);
      create index idx_workflow_approval_run on workflow_approval(user_id,run_id,status);
      create table workflow_node_event(
        id text primary key, run_id text not null, user_id uuid not null references auth.users(id) on delete cascade,
        node text not null, attempt integer not null default 1, status text not null,
        detail jsonb not null default '{}'::jsonb, started_at timestamptz not null default now(),
        completed_at timestamptz, foreign key(run_id,user_id) references workflow_execution(run_id,user_id) on delete cascade);
      create index idx_workflow_node_run on workflow_node_event(user_id,run_id,started_at);
      alter table workflow_execution enable row level security;
      alter table workflow_job enable row level security;
      alter table workflow_approval enable row level security;
      alter table workflow_node_event enable row level security;
      create policy "owner_only" on workflow_execution for all using(auth.uid()=user_id) with check(auth.uid()=user_id);
      create policy "owner_only" on workflow_job for all using(auth.uid()=user_id) with check(auth.uid()=user_id);
      create policy "owner_only" on workflow_approval for all using(auth.uid()=user_id) with check(auth.uid()=user_id);
      create policy "owner_only" on workflow_node_event for all using(auth.uid()=user_id) with check(auth.uid()=user_id);
    """)


def downgrade() -> None:
    raise RuntimeError("LangGraph workflow migration is intentionally irreversible")
