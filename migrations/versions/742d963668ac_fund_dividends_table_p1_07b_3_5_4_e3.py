"""fund_dividends table (P1-07b §3.5.4 E3)

Revision ID: 742d963668ac
Revises: 2467f55bb86e
Create Date: 2026-07-30 06:05:16.197077+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "742d963668ac"
down_revision: str | None = "2467f55bb86e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fund_dividends",
        sa.Column("code", sa.String(length=12), nullable=False),
        sa.Column("ex_date", sa.Date(), nullable=False),
        sa.Column("div_per_unit", sa.Numeric(precision=10, scale=6), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=True),
        sa.PrimaryKeyConstraint("code", "ex_date"),
    )


def downgrade() -> None:
    op.drop_table("fund_dividends")
