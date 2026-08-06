"""scheduler_jobs table (P1-10b §3.14.3)

Revision ID: f3a1c90e4b2d
Revises: 742d963668ac
Create Date: 2026-08-04 00:00:00.000000+00:00

新增 scheduler_jobs 表(详设§3.14.3 可选执行历史表)，记录定时/手动任务执行状态与耗时。
> 沿用本仓库 autogenerate 全表快照约定(与 742d963668ac 一致)：upgrade 重建全表+新增 scheduler_jobs。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "f3a1c90e4b2d"
down_revision: str | None = "742d963668ac"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scheduler_jobs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.String(length=64), nullable=False),
        sa.Column("job_name", sa.String(length=128), nullable=True),
        sa.Column("trigger", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "started_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("args", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("result_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_scheduler_jobs_job_id", "scheduler_jobs", ["job_id"], unique=False)

    op.create_index("ix_scheduler_jobs_status", "scheduler_jobs", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_scheduler_jobs_status", table_name="scheduler_jobs")

    op.drop_index("ix_scheduler_jobs_job_id", table_name="scheduler_jobs")

    op.drop_table("scheduler_jobs")
