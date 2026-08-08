"""Add deterministic chunks, local embeddings and semantic-index jobs.

Revision ID: 0004_semantic_index
Revises: 0003_document_ingestion
"""
from alembic import op

revision = "0004_semantic_index"
down_revision = "0003_document_ingestion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        create extension if not exists vector with schema extensions;

        alter table content_item
          add column index_status text,
          add column embedding_model text,
          add column index_version integer,
          add column chunk_count integer not null default 0,
          add column indexed_at timestamptz,
          add column index_error_code text,
          add column index_error_message text;

        update content_item
        set index_status = case when status = 'ready' then 'pending' else 'failed' end,
            index_error_code = case when status <> 'ready' then 'extraction_not_ready' end,
            index_error_message = case when status <> 'ready'
              then 'Text extraction must succeed before this document can be indexed.' end;
        alter table content_item alter column index_status set not null;
        alter table content_item add constraint ck_content_index_status
          check (index_status in ('pending', 'indexing', 'indexed', 'failed'));
        create index idx_content_item_user_index_status on content_item(user_id, index_status);

        create table document_chunk (
          id text primary key,
          user_id uuid not null references auth.users(id) on delete cascade,
          knowledge_base_id text not null,
          content_id text not null references content_item(id) on delete cascade,
          ordinal integer not null check (ordinal >= 0),
          text text not null check (btrim(text) <> ''),
          token_count integer not null check (token_count > 0 and token_count <= 480),
          page_start integer,
          page_end integer,
          text_hash text not null,
          embedding_model text not null,
          index_version integer not null,
          embedding extensions.vector(384) not null,
          created_at timestamptz not null default now(),
          unique (id, user_id),
          unique (content_id, index_version, ordinal),
          constraint fk_chunk_content_tenant foreign key (content_id, user_id)
            references content_item(id, user_id) on delete cascade,
          constraint fk_chunk_knowledge_tenant foreign key (knowledge_base_id, user_id)
            references knowledge_base(id, user_id)
        );
        create index idx_document_chunk_tenant_base on document_chunk(user_id, knowledge_base_id);
        create index idx_document_chunk_content on document_chunk(content_id, ordinal);
        create index idx_document_chunk_embedding_hnsw on document_chunk
          using hnsw (embedding extensions.vector_cosine_ops);
        alter table document_chunk enable row level security;
        create policy "owner_only" on document_chunk for all
          using (auth.uid() = user_id) with check (auth.uid() = user_id);

        create table indexing_job (
          id text primary key,
          user_id uuid not null references auth.users(id) on delete cascade,
          content_id text not null unique,
          status text not null default 'queued'
            check (status in ('queued', 'running', 'retry_wait', 'succeeded', 'failed')),
          attempt_count integer not null default 0,
          max_attempts integer not null default 3 check (max_attempts > 0),
          available_at timestamptz not null default now(),
          lease_owner text,
          lease_until timestamptz,
          last_error_code text,
          last_error_message text,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          completed_at timestamptz,
          constraint fk_indexing_job_content_tenant foreign key (content_id, user_id)
            references content_item(id, user_id) on delete cascade
        );
        create index idx_indexing_job_claim on indexing_job(status, available_at, lease_until, created_at);
        create index idx_indexing_job_user_status on indexing_job(user_id, status);
        alter table indexing_job enable row level security;
        create policy "owner_only" on indexing_job for all
          using (auth.uid() = user_id) with check (auth.uid() = user_id);

        insert into indexing_job (id, user_id, content_id)
        select gen_random_uuid()::text, user_id, id from content_item where status = 'ready';
    """)


def downgrade() -> None:
    raise RuntimeError("Semantic-index migration is intentionally irreversible")
