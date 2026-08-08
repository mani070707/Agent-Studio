"""Add tenant-owned conversational memory.

Revision ID: 0009_conversation_memory
Revises: 0008_langgraph_workflows
"""
from alembic import op

revision = "0009_conversation_memory"
down_revision = "0008_langgraph_workflows"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
      alter table agent add constraint uq_agent_id_user_memory unique(id,user_id);
      alter table run add constraint uq_run_id_user_memory unique(id,user_id);
      create table conversation_thread(
        id text primary key, user_id uuid not null references auth.users(id) on delete cascade,
        agent_id text not null references agent(id) on delete cascade,
        agent_version_id text not null references agent_version(id), title text not null,
        status text not null default 'active' check(status in ('active','archived')),
        memory_enabled boolean not null default true, summary jsonb not null default '{}'::jsonb,
        summarized_through_message_id text, summary_token_count integer not null default 0,
        message_token_count integer not null default 0, expires_at timestamptz not null,
        created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
        unique(id,user_id),
        foreign key(agent_id,user_id) references agent(id,user_id) on delete cascade,
        foreign key(agent_version_id,user_id) references agent_version(id,user_id));
      create index idx_conversation_thread_owner on conversation_thread(user_id,status,updated_at desc);
      create index idx_conversation_thread_agent on conversation_thread(user_id,agent_id,updated_at desc);
      create table conversation_message(
        id text primary key, user_id uuid not null references auth.users(id) on delete cascade,
        thread_id text not null, role text not null check(role in ('user','assistant')),
        content jsonb not null, run_id text,
        token_count integer not null default 0, created_at timestamptz not null default now(),
        foreign key(thread_id,user_id) references conversation_thread(id,user_id) on delete cascade,
        foreign key(run_id,user_id) references run(id,user_id));
      create index idx_conversation_message_thread on conversation_message(user_id,thread_id,created_at,id);
      alter table conversation_thread enable row level security;
      alter table conversation_message enable row level security;
      create policy "owner_only" on conversation_thread for all using(auth.uid()=user_id) with check(auth.uid()=user_id);
      create policy "owner_only" on conversation_message for all using(auth.uid()=user_id) with check(auth.uid()=user_id);
    """)


def downgrade() -> None:
    raise RuntimeError("Conversation-memory migration is intentionally irreversible")
