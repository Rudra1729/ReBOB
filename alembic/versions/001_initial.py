"""Initial schema — mirrors PostgresBackend.init_db()."""

from alembic import op

revision = "001"
down_revision = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    # Full DDL is applied by PostgresBackend.init_db() on first boot.
    # This revision exists for teams that prefer alembic-managed migrations.


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS sessions, api_tokens, embeddings, memory, organizations CASCADE")
