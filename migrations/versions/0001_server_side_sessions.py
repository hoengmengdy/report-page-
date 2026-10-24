"""Create encrypted server-side sessions.

Revision ID: 0001
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("browser_sessions",
                    sa.Column("id", sa.String(64), primary_key=True),
                    sa.Column("meta_user_id", sa.String(64), nullable=True),
                    sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
                    sa.Column("encrypted_payload", sa.Text(), nullable=False))
    op.create_index("ix_browser_sessions_meta_user_id", "browser_sessions", ["meta_user_id"])


def downgrade():
    op.drop_index("ix_browser_sessions_meta_user_id", table_name="browser_sessions")
    op.drop_table("browser_sessions")
