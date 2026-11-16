"""carátulas: columna cover_url y caché de búsquedas

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("track_entry", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("cover_url", sqlmodel.sql.sqltypes.AutoString(), nullable=True)
        )
    op.create_table(
        "artwork",
        sa.Column("key", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("url", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    op.drop_table("artwork")
    with op.batch_alter_table("track_entry", schema=None) as batch_op:
        batch_op.drop_column("cover_url")
