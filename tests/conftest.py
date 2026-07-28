"""pytest 公共夹具(开发规范§11)。"""

from __future__ import annotations

import os

# 测试环境隔离：在任何 app 导入前设定(§9.1)，避免读到本地 .env
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@localhost:5432/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from api.main import app  # noqa: E402


@pytest.fixture()
def client() -> TestClient:
    """FastAPI 测试客户端。"""
    return TestClient(app)
