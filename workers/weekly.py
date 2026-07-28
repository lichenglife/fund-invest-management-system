"""周报 worker 入口(详设§3.11.7 异步独立周报 / TP-06)。

计划任务：P3-03b 周报 worker(独立进程，失败降级)。
当前为骨架占位。

运行：``python -m workers.weekly``
TODO(P3-03b, FR-31/32/DC-008): RAG 周报生成；失败回退规则摘要(50303)。
"""

from __future__ import annotations

import logging

from config.settings import get_settings
from infra.logging import setup_logging

logger = logging.getLogger(__name__)


def main() -> None:
    s = get_settings()
    setup_logging(level=s.log_level, service="fundlens-weekly")
    logger.info("worker.weekly.ready", extra={"action": "weekly.init", "env": s.app_env})
    logger.warning("weekly.not_implemented", extra={"action": "weekly.run"})


if __name__ == "__main__":
    main()
