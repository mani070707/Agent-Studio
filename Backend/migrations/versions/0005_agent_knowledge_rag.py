"""Bind knowledge to versions and persist grounded RAG results.

Revision ID: 0005_agent_knowledge_rag
Revises: 0004_semantic_index
"""
from alembic import op

revision = "0005_agent_knowledge_rag"
down_revision = "0004_semantic_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        alter table agent_version add column user_id uuid;
        update agent_version av set user_id = a.user_id from agent a where a.id = av.agent_id;
        alter table agent_version alter column user_id set not null;
        alter table agent_version add constraint fk_agent_version_user
          foreign key (user_id) references auth.users(id) on delete cascade;
        alter table agent_version add constraint uq_agent_version_id_user unique (id, user_id);
        create index idx_agent_version_user on agent_version(user_id);
        alter table agent_version add column retrieval_config jsonb not null default
          jsonb_build_object('mode', 'hybrid', 'top_k', 6, 'max_per_document', 3,
                             'standard_context_tokens', 2500, 'free_context_tokens', 1200);

        create table agent_version_knowledge_base (
          agent_version_id text not null,
          knowledge_base_id text not null,
          user_id uuid not null references auth.users(id) on delete cascade,
          created_at timestamptz not null default now(),
          primary key (agent_version_id, knowledge_base_id),
          foreign key (agent_version_id, user_id) references agent_version(id, user_id) on delete cascade,
          foreign key (knowledge_base_id, user_id) references knowledge_base(id, user_id)
        );
        create index idx_version_knowledge_user on agent_version_knowledge_base(user_id, agent_version_id);
        alter table agent_version_knowledge_base enable row level security;
        create policy "owner_only" on agent_version_knowledge_base for all
          using (auth.uid() = user_id) with check (auth.uid() = user_id);

        insert into agent_version_knowledge_base (agent_version_id, knowledge_base_id, user_id)
        select av.id, kb.id, av.user_id
        from agent_version av
        join knowledge_base kb on kb.legacy_agent_id = av.agent_id and kb.user_id = av.user_id
        where av.tool_allowlist::jsonb ? 'search_documents'
        on conflict do nothing;

        alter table document_chunk add column search_vector tsvector
          generated always as (to_tsvector('english', text)) stored;
        create index idx_document_chunk_search_vector on document_chunk using gin(search_vector);

        alter table run add column citations jsonb not null default '[]'::jsonb;
        alter table run add column grounding_status text
          check (grounding_status is null or grounding_status in ('grounded', 'insufficient_evidence'));
        alter table run add column retrieval_stats jsonb not null default '{}'::jsonb;
    """)


def downgrade() -> None:
    raise RuntimeError("Grounded RAG migration is intentionally irreversible")
