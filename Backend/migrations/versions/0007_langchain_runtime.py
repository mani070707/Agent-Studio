"""Add versioned runtime engine observability.

Revision ID: 0007_langchain_runtime
Revises: 0006_rag_evaluation
"""
from alembic import op

revision = "0007_langchain_runtime"
down_revision = "0006_rag_evaluation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
      alter table run add column runtime_engine text not null default 'direct'
        check(runtime_engine in ('direct','langchain'));
      alter table run add column runtime_stats jsonb not null default '{}'::jsonb;
      create index idx_run_runtime_engine on run(user_id,runtime_engine,completed_at);
    """)


def downgrade() -> None:
    raise RuntimeError("LangChain runtime migration is intentionally irreversible")
