"""data_quality_log table (P1-01c §3.1.4)

Revision ID: 2467f55bb86e
Revises: e2de76ea9934
Create Date: 2026-07-29 06:15:25.729102+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2467f55bb86e"
down_revision: str | None = "e2de76ea9934"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "data_quality_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("entity", sa.String(length=32), nullable=True),
        sa.Column("check_date", sa.Date(), nullable=True),
        sa.Column("missing_count", sa.Integer(), nullable=True),
        sa.Column("anomaly_flag", sa.Boolean(), nullable=True),
        sa.Column("cv_error", sa.Numeric(precision=8, scale=4), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=True),
        sa.Column("as_of", sa.Date(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("data_quality_log")
