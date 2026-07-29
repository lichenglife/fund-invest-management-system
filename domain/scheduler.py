"""采集定时编排(P1-01d，详设§3.14 调度 / §3.14.2 工作日 18:00)。

APScheduler 编排定时采集任务(§3.14.2)；单实例运行(MVP)，多副本由分布式锁防重(§3.14.6)。

调度表(§3.14.2)：
- 工作日 18:00 增量采集(collect_all)

> MVP 仅编排采集；指标重算(P1-05)/周报(P3-03b)/舆情(P3-01b)/备份(P1-22)随各自任务落地。
"""

from __future__ import annotations

import logging
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

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


__all__: list[str] = ["build_scheduler", "COLLECT_CRON"]
