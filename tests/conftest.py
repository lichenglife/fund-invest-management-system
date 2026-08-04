"""pytest 公共夹具(开发规范§11)。

DB 测试隔离采用「会话级共享引擎 + 每用例 TRUNCATE」模式：
- 历史问题：11 个测试文件各自在 function-scope fixture 里 ``create_engine`` +
  ``drop_all/create_all``，单次全套运行触发数十次引擎创建/销毁与 DDL 风暴，
  打满 Postgres 连接 -> 间歇性、order-dependent 失败(连接耗尽 + 表被互相 drop)。
- 现方案：``db_engine``(session) 全程建表一次；``engine``/``db_session``(function)
  每用例 ``TRUNCATE ... CASCADE`` 清表，零 DDL、零连接耗尽，测试间数据完全隔离。
"""

from __future__ import annotations

import os
from collections.abc import Iterator

# 测试环境隔离：在任何 app 导入前设定(§9.1)，避免读到本地 .env
os.environ.setdefault("APP_ENV", "test")
# 指向 compose PG(宿主端口 15432，避让既有占用；见 .gitignore/DEFERRED D5)
os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://fundlens:changeme@localhost:15432/fundlens"
)
os.environ.setdefault("REDIS_URL", "redis://localhost:16379/15")
# 鉴权测试兜底 key(§2.19.6；生产走 env，测试用固定值)
os.environ.setdefault("AES_KEY", "00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("ADMIN_USERNAME", "admin")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import Engine, create_engine, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

import infra.db.models  # noqa: E402, F401  注册全部模型到 Base.metadata
from api.main import app  # noqa: E402
from infra.db import Base  # noqa: E402


@pytest.fixture()
def client() -> TestClient:
    """FastAPI 测试客户端(走全局 app；DB 端点用真实 SessionLocal，非 db 用例用)。"""
    return TestClient(app)


@pytest.fixture(scope="session")
def db_url() -> str:
    """测试库 URL(localhost:15432，避让既有占用，DEFERRED D5)。"""
    return os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+psycopg://fundlens:changeme@localhost:15432/fundlens",
    )


@pytest.fixture(scope="session")
def db_engine(db_url: str) -> Iterator[Engine]:
    """会话级共享引擎：建表一次(消除每用例 create_engine/drop_all/create_all 的连接耗尽与 DDL 风暴)。

    全库 drop+create 仅在会话起止各一次；用例间数据隔离由 ``truncate_all`` 保证。
    """
    eng = create_engine(
        db_url,
        pool_pre_ping=True,  # 连接前 ping，避免断连(§8.5)
        pool_size=5,
        max_overflow=10,
        future=True,
    )
    Base.metadata.drop_all(eng, checkfirst=True)
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


def truncate_all(engine: Engine) -> None:
    """清空全部表(CASCADE + RESTART IDENTITY)，保证用例间数据隔离(替代每用例 drop/create)。

    按依赖逆序(子表先)TRUNCATE；CASCADE 使外键约束表一并清空；RESTART IDENTITY 重置序列，
    便于断言自增主键的用例。仅清 ORM 映射表，不动 alembic_version。
    """
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(text(f"TRUNCATE TABLE {table.name} RESTART IDENTITY CASCADE"))


@pytest.fixture()
def engine(db_engine: Engine) -> Iterator[Engine]:
    """每用例：truncate 清表后返回共享引擎(替代各文件自建 engine + drop/create)。

    供 collect/batch/models 等直接用 ``Session(engine)`` 或 monkeypatch SessionLocal 的用例。
    """
    truncate_all(db_engine)
    yield db_engine


@pytest.fixture()
def db_session(db_engine: Engine) -> Iterator[Session]:
    """每用例：truncate 清表 + 返回绑定共享引擎的 Session(供 API 集成用例种子数据)。

    API 用例的 ``client_with_*`` 依赖本夹具写入种子数据；请求期由各自 override 的
    ``get_db`` 另建 Session(同引擎)处理。
    """
    truncate_all(db_engine)
    sess = Session(bind=db_engine)
    try:
        yield sess
    finally:
        sess.close()
