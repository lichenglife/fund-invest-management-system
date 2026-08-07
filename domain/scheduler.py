"""采集定时编排(P1-01d，详设§3.14 调度 / §3.14.2 工作日 18:00)。

APScheduler 编排定时采集任务(§3.14.2)；单实例运行(MVP)，多副本由分布式锁防重(§3.14.6)。

调度表(§3.14.2)：
- 工作日 18:00 增量采集(collect_all)

> MVP 仅编排采集；指标重算(P1-05)/周报(P3-03b)/舆情(P3-01b)/备份(P1-22)随各自任务落地。
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

#: 工作日 18:00 增量采集(§3.14.2)
COLLECT_CRON = "0 18 * * 1-5"


def build_scheduler(jobs: list[dict[str, Any]]) -> BackgroundScheduler:
    """构建调度器(§3.14)。

    Args:
        jobs: 作业列表，每项 {"id","func","cron","args"}。
            - id: 作业标识(唯一)。
            - func: 可调用对象。
            - cron: 5 字段 cron 表达式(§3.14.2)。
            - args: 传给 func 的参数(list)。
    Returns:
        未启动的 BackgroundScheduler(由调用方 start/shutdown)。
    """
    scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
    for job in jobs:
        trigger = CronTrigger.from_crontab(job["cron"])
        scheduler.add_job(
            func=job["func"],
            trigger=trigger,
            id=job["id"],
            args=job.get("args", []),
            replace_existing=True,  # 重启时覆盖旧作业(幂等)
            max_instances=1,  # 单实例不重叠(§3.14.6)
            misfire_grace_time=300,  # 错过 5 min 内仍补跑
        )
        logger.info("scheduler.job_added", extra={"action": "schedule", "job_id": job["id"]})
    return scheduler


# ---------------------------------------------------------------------------
# 任务执行记录(§3.14.3 scheduler_jobs / §3.14.5 失败告警)
# ---------------------------------------------------------------------------

#: ``error`` 字段截断长度(Text；§9 安全：仅存异常摘要，不存堆栈/SQL)。
ERROR_MAX_LEN = 2000

#: 会话工厂类型(调用返一个 Session)。
SessionFactory = Callable[[], "Session"]


@dataclass
class JobRunHandle:
    """任务执行记录句柄(供调用方在正常退出前设置 ``result_summary``)。

    Attributes:
        job_pk: scheduler_jobs 行主键(insert 后回填)。
        job_id: 作业标识。
        started_at: 开始时间(UTC)。
        result_summary: 成功摘要(如 {"funds": N}；调用方设置)。
        error: 失败异常摘要(异常路径自动填充)。
    """

    job_pk: int | None = None
    job_id: str = ""
    started_at: datetime | None = None
    result_summary: dict[str, Any] | None = None
    error: str | None = None


@contextmanager
def record_job_run(
    job_id: str,
    job_name: str | None = None,
    *,
    trigger: str = "cron",
    args: dict[str, Any] | None = None,
    session_factory: SessionFactory | None = None,
) -> Iterator[JobRunHandle]:
    """记录任务执行到 ``scheduler_jobs``(§3.14.3 / §3.14.5)。

    开始即写 ``status=running`` 行；正常退出写 ``success`` + ``result_summary`` + ``duration_ms``；
    异常写 ``failed`` + ``error``(摘要，不含堆栈 §9)并 **re-raise**。
    用**独立 session**(不与业务事务绑定，业务回滚也保留执行记录)。

    Args:
        job_id: 作业标识(collect_all / fund_recalc / collect_nav ...)。
        job_name: 人类可读名。
        trigger: cron(定时) / manual(手动 trigger-job §3.14.4)。
        args: 触发参数快照。
        session_factory: 会话工厂(默认 ``infra.db.session.SessionLocal``，懒导入；
            测试可注入绑定测试引擎的工厂)。
    用法::

        with record_job_run("collect_all", "增量采集", trigger="cron") as run:
            result = do_work()
            run.result_summary = result
    """
    started = datetime.now(UTC)
    handle = JobRunHandle(job_id=job_id, started_at=started)
    sf = session_factory if session_factory is not None else _default_session_factory
    _insert_running(sf, handle, job_name=job_name, trigger=trigger, args=args)
    try:
        yield handle
    except Exception as exc:
        handle.error = _truncate(str(exc))
        _finalize(sf, handle, status="failed")
        raise
    else:
        _finalize(sf, handle, status="success")


def _default_session_factory() -> Session:
    """默认会话工厂：懒导入 ``SessionLocal``(避免 domain 导入期依赖 infra)。"""
    from infra.db.session import SessionLocal

    return SessionLocal()


def _insert_running(
    sf: SessionFactory,
    handle: JobRunHandle,
    *,
    job_name: str | None,
    trigger: str,
    args: dict[str, Any] | None,
) -> None:
    """写 status=running 行并回填 job_pk。"""
    from infra.db.models.scheduler import SchedulerJob

    with sf() as db:
        row = SchedulerJob(
            job_id=handle.job_id,
            job_name=job_name,
            trigger=trigger,
            status="running",
            started_at=handle.started_at,
            args=args,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        handle.job_pk = row.id


def _finalize(sf: SessionFactory, handle: JobRunHandle, *, status: str) -> None:
    """更新执行行终态(success/failed + finished_at + duration_ms + result/error)。"""
    from infra.db.models.scheduler import SchedulerJob

    if handle.job_pk is None or handle.started_at is None:
        return
    finished = datetime.now(UTC)
    duration_ms = int((finished - handle.started_at).total_seconds() * 1000)
    with sf() as db:
        row = db.get(SchedulerJob, handle.job_pk)
        if row is None:
            return
        row.status = status
        row.finished_at = finished
        row.duration_ms = duration_ms
        if status == "success":
            row.result_summary = handle.result_summary
        else:
            row.error = handle.error
        db.commit()


def _truncate(text: str) -> str:
    """截断异常摘要(§9 不存完整堆栈)。"""
    return text[:ERROR_MAX_LEN]


__all__: list[str] = ["build_scheduler", "COLLECT_CRON", "record_job_run", "JobRunHandle"]
