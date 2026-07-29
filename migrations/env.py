"""Alembic 迁移环境(详设§2.7 / §2.20；开发规范§9.3)。

- target_metadata = Base.metadata：autogenerate 检测 infra.db.models 注册的全部表。
- DB URL 从 config.settings(DATABASE_URL env)注入；alembic.ini 的值仅兜底。
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# 仓库根加入 sys.path，使 migrations/ 可 import infra/config
_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import infra.db.models  # noqa: E402,F401  注册 ORM 到 metadata
from config.settings import get_settings  # noqa: E402
from infra.db import Base  # noqa: E402

config = context.config

# 注入运行时 DB URL(覆盖 alembic.ini 占位)
config.set_main_option("sqlalchemy.url", get_settings().database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# autogenerate 比对目标(全量表)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """离线模式：生成 SQL 脚本(不连库)。"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式：连库执行迁移。"""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
