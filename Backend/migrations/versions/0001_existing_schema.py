"""Existing Agent Studio schema baseline.

Fresh Supabase projects run the two baseline SQL assets. Existing projects must use
`alembic stamp 0001_existing_schema` once, then use `alembic upgrade head` normally.
"""
from pathlib import Path

from alembic import op

revision = "0001_existing_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    root = Path(__file__).resolve().parents[1]
    connection = op.get_bind()
    raw = connection.connection
    cursor = raw.cursor()
    try:
        for filename in ("001_init.sql", "002_provider_connections.sql"):
            cursor.execute((root / filename).read_text(encoding="utf-8"))
    finally:
        cursor.close()


def downgrade() -> None:
    raise RuntimeError("The production baseline is intentionally irreversible")
