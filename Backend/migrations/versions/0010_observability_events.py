"""Add durable operational events and worker heartbeats.

Revision ID: 0010_observability_events
Revises: 0009_conversation_memory
"""
from alembic import op

revision = "0010_observability_events"
down_revision = "0009_conversation_memory"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
      create table activity_event(
        id bigint generated always as identity primary key,
        user_id uuid not null references auth.users(id) on delete cascade,
        resource_type text not null, resource_id text not null, event_type text not null,
        payload jsonb not null default '{}'::jsonb, trace_id text not null,
        correlation_id text, created_at timestamptz not null default now());
      create index idx_activity_event_owner_replay on activity_event(user_id,id);
      create index idx_activity_event_resource on activity_event(user_id,resource_type,resource_id,id);
      create index idx_activity_event_created on activity_event(created_at);
      alter table activity_event enable row level security;
      create policy "owner_only" on activity_event for select using(auth.uid()=user_id);
      create policy "owner_insert" on activity_event for insert with check(auth.uid()=user_id);
      create table worker_heartbeat(
        id text primary key, worker_type text not null, instance_id text not null,
        status text not null default 'online', metadata jsonb not null default '{}'::jsonb,
        started_at timestamptz not null default now(), last_seen_at timestamptz not null default now(),
        unique(worker_type,instance_id));
      create index idx_worker_heartbeat_type_seen on worker_heartbeat(worker_type,last_seen_at desc);
    """)


def downgrade() -> None:
    raise RuntimeError("Observability event migration is intentionally irreversible")
