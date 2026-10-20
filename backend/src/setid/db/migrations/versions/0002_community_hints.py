"""community hints

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "community_hint",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column(
            "kind",
            sa.Enum("tracklist", "comment", "reply", name="hintkind", native_enum=False, length=20),
            nullable=False,
        ),
        sa.Column("start_s", sa.Float(), nullable=True),
        sa.Column("artist", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("title", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("unreleased", sa.Boolean(), nullable=False),
        sa.Column("origin", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("author", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("likes", sa.Integer(), nullable=False),
        sa.Column("text", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["job.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("community_hint", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_community_hint_job_id"), ["job_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("community_hint", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_community_hint_job_id"))
    op.drop_table("community_hint")
