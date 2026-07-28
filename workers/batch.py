"""批算 worker 入口(详设§3.3.9 批量计算并发与缓存设计 / TP-01 §4)。

计划任务：P1-05 夜算批(评分，多进程)。
当前为骨架占位。

运行：``python -m workers.batch``
TODO(P1-05, FR-07/DC-003): batch_score_all 全市场分位表写 PG + 刷 Redis(ADR-002)。
"""

from __future__ import annotations

import logging

from config.settings import get_settings
from infra.logging import setup_logging

logger = logging.getLogger(__name__)


def main() -> None:
    s = get_settings()
    setup_logging(level=s.log_level, service="fundlens-batch")
    logger.info("worker.batch.ready", extra={"action": "batch.init", "env": s.app_env})
    logger.warning("batch.not_implemented", extra={"action": "batch.run"})


if __name__ == "__main__":
    main()
