"""preescuchas y tracks vistos

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("track_entry", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("preview_url", sqlmodel.sql.sqltypes.AutoString(), nullable=True)
        )
    # Es una caché: se vacía para que los tracks ya buscados se vuelvan a buscar, ahora
    # también con su preescucha.
    op.execute("DELETE FROM artwork")
    with op.batch_alter_table("artwork", schema=None) as batch_op:
        batch_op.alter_column("url", new_column_name="cover_url")
        batch_op.add_column(
            sa.Column("preview_url", sqlmodel.sql.sqltypes.AutoString(), nullable=True)
        )
    op.create_table(
        "seen_track",
        sa.Column("key", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    op.drop_table("seen_track")
    with op.batch_alter_table("artwork", schema=None) as batch_op:
        batch_op.drop_column("preview_url")
        batch_op.alter_column("cover_url", new_column_name="url")
    with op.batch_alter_table("track_entry", schema=None) as batch_op:
        batch_op.drop_column("preview_url")
