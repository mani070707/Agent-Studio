"""Add deterministic RAG evaluation and durable quality gates.

Revision ID: 0006_rag_evaluation
Revises: 0005_agent_knowledge_rag
"""
from alembic import op

revision = "0006_rag_evaluation"
down_revision = "0005_agent_knowledge_rag"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
      alter table evaluation_dataset add column user_id uuid;
      update evaluation_dataset d set user_id=a.user_id from agent a where a.id=d.agent_id;
      alter table evaluation_dataset alter column user_id set not null;
      alter table evaluation_dataset add constraint fk_eval_dataset_user foreign key(user_id) references auth.users(id) on delete cascade;
      alter table evaluation_dataset add column description text not null default '';
      alter table evaluation_dataset add column retrieval_recall_threshold double precision not null default 0.8;
      alter table evaluation_dataset add column citation_precision_threshold double precision not null default 1.0;
      alter table evaluation_dataset add column grounding_threshold double precision not null default 1.0;
      alter table evaluation_dataset add column status text not null default 'active' check(status in ('active','archived'));
      alter table evaluation_dataset add column created_at timestamptz not null default now();
      alter table evaluation_dataset add column updated_at timestamptz not null default now();
      alter table evaluation_dataset add constraint uq_eval_dataset_id_user unique(id,user_id);
      create index idx_eval_dataset_user_status on evaluation_dataset(user_id,status);

      alter table evaluation_case add column expected_document_ids jsonb not null default '[]'::jsonb;
      alter table evaluation_case add column expected_chunk_ids jsonb not null default '[]'::jsonb;
      alter table evaluation_case add column retrieval_k integer not null default 6 check(retrieval_k between 1 and 20);

      alter table evaluation_run add column user_id uuid;
      update evaluation_run er set user_id=av.user_id from agent_version av where av.id=er.agent_version_id;
      alter table evaluation_run alter column user_id set not null;
      alter table evaluation_run add constraint fk_eval_run_user foreign key(user_id) references auth.users(id) on delete cascade;
      alter table evaluation_run add column completed_cases integer not null default 0;
      alter table evaluation_run add column total_cases integer not null default 0;
      alter table evaluation_run add column metrics jsonb not null default '{}'::jsonb;
      alter table evaluation_run add column gate_results jsonb not null default '{}'::jsonb;
      alter table evaluation_run add column config_snapshot jsonb not null default '{}'::jsonb;
      alter table evaluation_run add column dataset_snapshot jsonb not null default '[]'::jsonb;
      alter table evaluation_run add column attempt_count integer not null default 0;
      alter table evaluation_run add column max_attempts integer not null default 3;
      alter table evaluation_run add column available_at timestamptz not null default now();
      alter table evaluation_run add column lease_owner text;
      alter table evaluation_run add column lease_until timestamptz;
      alter table evaluation_run add column error_code text;
      alter table evaluation_run add column error_message text;
      alter table evaluation_run add column created_at timestamptz not null default now();
      alter table evaluation_run add column started_at timestamptz;
      alter table evaluation_run add column completed_at timestamptz;
      update evaluation_run set status=case when status='pending' then 'queued' else status end;
      alter table evaluation_run add constraint ck_eval_run_status check(status in ('queued','running','passed','failed','retry_wait'));
      alter table evaluation_run add constraint uq_eval_run_id_user unique(id,user_id);
      create index idx_eval_run_queue on evaluation_run(status,available_at,created_at);
      create index idx_eval_run_user_version on evaluation_run(user_id,agent_version_id,created_at desc);

      create table evaluation_case_result(
        id text primary key,
        user_id uuid not null references auth.users(id) on delete cascade,
        evaluation_run_id text not null,
        evaluation_case_id text not null,
        run_id text references run(id) on delete set null,
        status text not null default 'completed',
        retrieved_sources jsonb not null default '[]'::jsonb,
        expected_evidence jsonb not null default '{}'::jsonb,
        metrics jsonb not null default '{}'::jsonb,
        field_mismatches jsonb not null default '[]'::jsonb,
        latency_ms integer not null default 0,
        token_usage jsonb not null default '{}'::jsonb,
        error_code text,
        error_message text,
        created_at timestamptz not null default now(),
        unique(evaluation_run_id,evaluation_case_id),
        foreign key(evaluation_run_id,user_id) references evaluation_run(id,user_id) on delete cascade
      );
      create index idx_eval_case_result_run on evaluation_case_result(user_id,evaluation_run_id);
      alter table evaluation_case_result enable row level security;
      create policy "owner_only" on evaluation_case_result for all using(auth.uid()=user_id) with check(auth.uid()=user_id);
    """)


def downgrade() -> None:
    raise RuntimeError("RAG evaluation migration is intentionally irreversible")
