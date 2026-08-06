"""初始化数据库表(MVP 首次部署，§2.20 / §2.7)。

创建全部 ORM 映射表(等价 ``Base.metadata.create_all``，与测试同口径)。

> 说明：alembic 迁移链存在 autogenerate 重复建表问题(各 migration 均重复 create 全部
> 核心表，``alembic upgrade head`` 在干净库上 DuplicateTable)，属 P0-04b 待修。
> MVP 部署「一键起」先用本脚本 create_all 保证可靠；schema 演进待迁移链修复后回归 alembic。

运行：``python scripts/init_db.py``（DATABASE_URL 经 env 注入）
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# 仓库根加入 sys.path，使 config/infra 可 import(同 migrations/env.py)
_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sqlalchemy import create_engine  # noqa: E402

import infra.db.models  # noqa: F401,E402  注册全部模型到 Base.metadata
from config.settings import get_settings  # noqa: E402
from infra.db import Base  # noqa: E402

logger = logging.getLogger(__name__)


def main() -> None:
    url = get_settings().database_url
    engine = create_engine(url, pool_pre_ping=True)
    Base.metadata.create_all(engine)
    n = len(Base.metadata.tables)
    logger.info(
        "init_db.created", extra={"action": "init_db", "tables": n, "url_host": url.split("@")[-1]}
    )
    print(f"[init_db] {n} tables created on {url.split('@')[-1]}")


if __name__ == "__main__":
    main()
