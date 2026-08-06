"""数据库迁移入口(MVP 部署「一键起」，§2.20 / §2.7)。

走 alembic 迁移链(P0-04b 已修：各 migration 只建本任务新增表，干净库 ``alembic upgrade head`` 通过)：
- 干净库：``alembic upgrade head`` 建全部 14 表(经 5 个 migration 顺序应用)。
- 已由 create_all 建表但无 alembic_version(历史 dev/早期部署)：先 ``stamp head`` 收编，再 upgrade(无-op)。
- alembic 已管理库：``upgrade head`` 增量应用待办迁移。

> create_all 仅保留给测试(conftest db_engine)做隔离建表；部署路径走 alembic 以支持 schema 演进
> (后续 schema 变更走 ``alembic revision``，而非重建全表)。
> 迁移链与 create_all 产物已逐列/逐索引比对一致(0 drift)，见 REVIEW_20260806 A1。

运行：``python scripts/init_db.py``（DATABASE_URL 经 env 注入）
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# 仓库根加入 sys.path，使 config/infra/alembic 可 import(同 migrations/env.py)
_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import create_engine, inspect  # noqa: E402

import infra.db.models  # noqa: F401,E402  注册全部模型(env.py autogenerate/比对需 metadata)
from config.settings import get_settings  # noqa: E402

logger = logging.getLogger(__name__)

_MIGRATIONS_DIR = Path(_REPO_ROOT) / "migrations"


def main() -> None:
    url = get_settings().database_url
    engine = create_engine(url, pool_pre_ping=True)

    cfg = Config()
    cfg.set_main_option("script_location", str(_MIGRATIONS_DIR))
    # env.py 会以 get_settings().database_url 覆盖；此处显式设置便于离线/日志
    cfg.set_main_option("sqlalchemy.url", url)

    existing = set(inspect(engine).get_table_names())
    has_alembic_version = "alembic_version" in existing
    app_tables_present = bool(existing - {"alembic_version"})

    host = url.split("@")[-1]

    # 历史 create_all 部署(有表但未纳入 alembic)：stamp head 收编，避免 upgrade 重复建表报错
    if not has_alembic_version and app_tables_present:
        command.stamp(cfg, "head")
        logger.info(
            "init_db.stamped",
            extra={"action": "init_db", "tables": len(existing), "adopted": True, "url_host": host},
        )
        print(f"[init_db] stamped head (adopted {len(existing)} existing tables) on {host}")
        return

    # 干净库或 alembic 已管理库：顺序应用迁移
    command.upgrade(cfg, "head")
    n = len(inspect(engine).get_table_names())
    logger.info(
        "init_db.upgraded",
        extra={"action": "init_db", "tables": n, "adopted": False, "url_host": host},
    )
    print(f"[init_db] alembic upgrade head -> {n} tables on {host}")


if __name__ == "__main__":
    main()
