"""pytest 公共夹具(开发规范§11)。"""

from __future__ import annotations

import os

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

from api.main import app  # noqa: E402


@pytest.fixture()
def client() -> TestClient:
    """FastAPI 测试客户端。"""
    return TestClient(app)


@pytest.fixture()
def db_url() -> str:
    """测试库 URL(localhost:15432，避让既有占用，DEFERRED D5)。"""
    return os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+psycopg://fundlens:changeme@localhost:15432/fundlens",
    )
