"""Add durable document-ingestion lifecycle and jobs.

Revision ID: 0003_document_ingestion
Revises: 0002_knowledge_bases
"""
from alembic import op

revision = "0003_document_ingestion"
down_revision = "0002_knowledge_bases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        alter table content_item
          add column status text,
          add column mime_type text,
          add column size_bytes bigint,
          add column content_hash text,
          add column page_count integer,
          add column character_count integer,
          add column extraction_version integer not null default 1,
          add column error_code text,
          add column error_message text,
          add column created_at timestamptz not null default now(),
          add column updated_at timestamptz not null default now();

        update content_item
        set status = case when btrim(extracted_text) <> '' then 'ready' else 'failed' end,
            character_count = case when btrim(extracted_text) <> '' then length(extracted_text) else 0 end,
            error_code = case when btrim(extracted_text) = '' then 'legacy_empty_content' end,
            error_message = case when btrim(extracted_text) = ''
              then 'This legacy document contains no extracted text. Upload it again to retry.' end;

        alter table content_item alter column status set not null;
        alter table content_item add constraint ck_content_ingestion_status
          check (status in ('queued', 'processing', 'ready', 'failed'));
        alter table content_item add constraint uq_content_id_user unique (id, user_id);
        create index idx_content_item_user_status on content_item(user_id, status);
        create unique index uq_content_item_active_hash
          on content_item(knowledge_base_id, content_hash)
          where content_hash is not null and status in ('queued', 'processing', 'ready');

        create table ingestion_job (
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
          constraint fk_ingestion_job_content_tenant
            foreign key (content_id, user_id) references content_item(id, user_id) on delete cascade
        );
        create index idx_ingestion_job_claim
          on ingestion_job(status, available_at, lease_until, created_at);
        create index idx_ingestion_job_user_status on ingestion_job(user_id, status);

        alter table ingestion_job enable row level security;
        create policy "owner_only" on ingestion_job for all
          using (auth.uid() = user_id)
          with check (auth.uid() = user_id);
    """)


def downgrade() -> None:
    raise RuntimeError("Document-ingestion lifecycle migration is intentionally irreversible")
