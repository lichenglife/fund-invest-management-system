"""调度任务执行历史 ORM 模型(详设§3.14.3 可选 scheduler_jobs 表)。

§3.14.3：可选 ``scheduler_jobs`` 表记录任务执行历史与状态。
§3.14.5：所有定时任务写入日志，失败告警；任务幂等设计，避免重复采集。
每行 = 一次任务执行(cron 触发或 manual 手动触发)；由 ``domain.scheduler.record_job_run``
在作业开始/结束时写入(§3.14.2 APScheduler 编排)。

> 命名沿用详设§3.14.3 ``scheduler_jobs``；表为执行历史(每行一次执行)，非作业定义。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import TIMESTAMP, BigInteger, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from infra.db.base import Base


class SchedulerJob(Base):
    """调度任务执行历史表(详设§3.14.3)。

    记录每次定时/手动任务的执行状态、耗时与错误摘要(§3.14.5 安全溯源)。
    不记堆栈/SQL(开发规范§9 安全)；``error`` 仅存异常摘要。
    """

    __tablename__ = "scheduler_jobs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # 作业标识(§3.14.2)：collect_all / fund_recalc / weekly_report / sentiment / valuation_signal / backup
    job_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    job_name: Mapped[str | None] = mapped_column(String(128))  # 人类可读名
    # 触发来源：cron(定时) / manual(手动 trigger-job §3.14.4)
    trigger: Mapped[str] = mapped_column(String(16), nullable=False, default="cron")
    # 执行状态：running / success / failed
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running", index=True)
    started_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)  # 耗时毫秒
    error: Mapped[str | None] = mapped_column(Text)  # 失败异常摘要(不含堆栈/SQL §9)
    args: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # 触发参数
    result_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # 成功摘要如 {upserted: N}
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )


__all__: list[str] = ["SchedulerJob"]
