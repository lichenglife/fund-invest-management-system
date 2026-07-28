"""引擎与会话工厂(§2.7 SQLAlchemy 2.x)。

``create_engine`` 不在导入时连接(惰性)，DB 不可用时不阻断导入；
实际连接失败在请求时由 ``get_db`` 捕获并映射 50302(§8.5 降级)。
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from config.settings import settings
from schemas.errors import ErrorCode, ExternalError

# engine 与 SessionLocal 在导入时创建(惰性连接，URL 来自 settings)。
engine: Engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,  # 连接前 ping，避免断连(§8.5)
    pool_size=5,
    max_overflow=10,
    future=True,
)

SessionLocal: sessionmaker[Session] = sessionmaker(
    bind=engine, autocommit=False, autoflush=False, expire_on_commit=False
)


def get_db() -> Iterator[Session]:
    """FastAPI 依赖：提供事务边界会话(§8.4)。

    失败映射 50302(§8.5 DB 降级)；业务层在事务边界内写，部分失败整体回滚。
    """
    db = SessionLocal()
    try:
        yield db
    except Exception as exc:  # noqa: BLE001  -> 包装为项目异常(§8.1)
        db.rollback()
        raise ExternalError(
            "数据库暂时不可用，请稍后重试",
            code=ErrorCode.DB_UNAVAILABLE,
            cause=exc,
        ) from exc
    finally:
        db.close()


def get_engine() -> Engine:
    """暴露引擎(供 worker/批算复用，ADR-002)。"""
    return engine


__all__: list[str] = ["engine", "SessionLocal", "get_db", "get_engine"]
