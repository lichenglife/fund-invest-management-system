"""采集 worker 入口(详设§3.1 数据采集与质量监控 / §3.1.8 并发采集)。

计划任务：P1-01a~d + P1-01d 定时编排(18:00)。
当前为骨架占位：初始化日志，打印就绪状态，不执行真实采集。

运行：``python -m workers.collect``
TODO(P1-01a, FR-36/46): AkShare 适配器 + 清洗 + upsert + 质量日志。
TODO(P1-01d, FR-36): APScheduler 18:00 触发编排。
"""

from __future__ import annotations

import logging

from config.settings import get_settings
from infra.logging import setup_logging

logger = logging.getLogger(__name__)


def main() -> None:
    s = get_settings()
    setup_logging(level=s.log_level, service="fundlens-collect")
    logger.info(
        "worker.collect.ready",
        extra={"action": "collect.init", "env": s.app_env},
    )
    # TODO(P1-01a~d): 实现采集链路
    logger.warning("collect.not_implemented", extra={"action": "collect.run"})


if __name__ == "__main__":
    main()
