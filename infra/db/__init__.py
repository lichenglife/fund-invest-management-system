"""infra.db 包 · SQLAlchemy 2.x 引擎与会话(详设§2.7 / §2.20 数据模型)。

模型(对应§2.20 表)在 ``models/`` 下；导入本包即注册到 ``Base.metadata``。
"""

from infra.db import models  # noqa: F401  注册 ORM 到 Base.metadata(供 Alembic autogenerate)
from infra.db.base import Base
from infra.db.session import SessionLocal, engine, get_db, get_engine

__all__: list[str] = ["Base", "engine", "SessionLocal", "get_db", "get_engine", "models"]
