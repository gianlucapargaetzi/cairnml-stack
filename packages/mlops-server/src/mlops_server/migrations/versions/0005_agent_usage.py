"""agent usage

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agents", sa.Column("usage", sa.JSON(), nullable=True))
    op.add_column("agents", sa.Column("usage_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("agents", "usage_at")
    op.drop_column("agents", "usage")
