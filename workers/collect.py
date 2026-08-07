"""采集 worker 入口(详设§3.1 数据采集 / §3.14 调度 / §3.14.2 工作日18:00)。

P1-01d：APScheduler 编排定时采集；可手动单次运行(``python -m workers.collect``)或
常驻调度(``python -m workers.collect --scheduler``)。

> MVP 单实例；多副本由分布式锁防重(§3.14.6)。
"""

from __future__ import annotations

import logging
import sys

from config.settings import get_settings
from infra.db.session import SessionLocal
from infra.logging import setup_logging

logger = logging.getLogger(__name__)


def run_once(codes: list[str] | None = None, *, trigger: str = "manual") -> None:
    """单次采集(名单 + 指定 codes 净值/重仓)；执行结果落库 scheduler_jobs(§3.14.3)。"""
    from datetime import date

    from domain.collect_service import CollectService
    from domain.scheduler import record_job_run

    codes = codes or []
    today = date.today().strftime("%Y%m%d")
    with record_job_run(
        "collect_all", "增量采集(名单+净值+重仓)", trigger=trigger, args={"codes": codes}
    ) as run:
        with SessionLocal() as db:
            service = CollectService(db)
            result = service.collect_all(codes, start=today, end=today)
        run.result_summary = result
    logger.info(
        "collect.run_done",
        extra={"action": "collect", "funds": result["funds"], "navs": result["navs"]},
    )


def run_scheduler() -> None:
    """常驻调度(§3.14.2 工作日 18:00 增量采集)。"""
    import signal

    from domain.scheduler import COLLECT_CRON, build_scheduler

    def _cron_collect() -> None:
        """定时触发(cron)，与手动 run_once 区分 trigger 落库(§3.14.4)。"""
        run_once(trigger="cron")

    scheduler = build_scheduler(
        jobs=[
            {
                "id": "collect_all",
                "func": _cron_collect,
                "cron": COLLECT_CRON,
                "args": [],
            }
        ]
    )
    scheduler.start()
    logger.info("collect.scheduler_started", extra={"action": "scheduler", "cron": COLLECT_CRON})

    # 优雅退出
    def _shutdown(signum: int, frame: object) -> None:  # noqa: ARG001
        logger.info("collect.scheduler_stopping", extra={"action": "scheduler", "sig": signum})
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)
    # 保持进程
    import time

    while scheduler.running:
        time.sleep(60)


def main() -> None:
    s = get_settings()
    setup_logging(level=s.log_level, service="fundlens-collect")
    if "--scheduler" in sys.argv:
        run_scheduler()
    else:
        run_once()


if __name__ == "__main__":
    main()
