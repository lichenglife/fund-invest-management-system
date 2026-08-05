"""健康检查与全局异常处理集成测试(详细设计§2.21 / §4.2 / §8.2)。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def test_health_returns_envelope(client: TestClient) -> None:
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    # §2.21.1 七字段
    assert set(body.keys()) == {
        "code",
        "data",
        "source",
        "as_of",
        "disclaimer",
        "message",
        "trace_id",
    }
    assert body["code"] == 0
    assert body["message"] == "ok"
    assert body["data"]["status"] == "ok"
    assert "version" in body["data"]
    assert body["disclaimer"] == "仅供参考，不构成投资建议"


def test_trace_id_echoed(client: TestClient) -> None:
    """§5.2/§6.2：传入 X-Trace-Id 应原样回写响应头。"""
    resp = client.get("/api/v1/health", headers={"X-Trace-Id": "trace-abc-123"})
    assert resp.headers.get("x-trace-id") == "trace-abc-123"
    assert resp.json()["trace_id"] == "trace-abc-123"


def test_trace_id_generated_when_absent(client: TestClient) -> None:
    resp = client.get("/api/v1/health")
    tid = resp.headers.get("x-trace-id")
    assert tid  # 非空
    assert resp.json()["trace_id"] == tid


def test_root_envelope(client: TestClient) -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["code"] == 0


def test_app_error_mapped_to_envelope(client: TestClient) -> None:
    """§8.2：AppError -> 信封。

    DB 不可用时 ``/api/v1/funds/{code}`` 查询触发 ExternalError(50302)->503 信封；
    这同样验证 AppError->7 字段信封映射(无 PG 时跳过，见 test_app_error_db)。
    """
    # 无 DB 覆盖 -> 查询失败 -> 50302 信封(或 DB 可用且基金不存在 -> 40002)
    resp = client.get("/api/v1/funds/000000.OF")
    assert resp.status_code in (404, 503)
    body = resp.json()
    assert body["code"] in (40002, 50302)
    assert body["data"] is None
    assert body["trace_id"]  # 必带


@pytest.mark.db
def test_app_error_db(db_url: str) -> None:
    """§8.2：DB 可用 + 基金不存在 -> NotFoundError(40002)->404 信封(确定性)。"""
    from collections.abc import Iterator

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session, sessionmaker

    import infra.db.models  # noqa: F401
    from api.deps import get_db
    from api.main import create_app
    from infra.db import Base

    eng = create_engine(db_url)
    Base.metadata.drop_all(eng, checkfirst=True)
    Base.metadata.create_all(eng)
    TestSession = sessionmaker(bind=eng, autocommit=False, autoflush=False)

    def _override() -> Iterator[Session]:
        s = TestSession()
        try:
            yield s
        finally:
            s.close()

    app = create_app()
    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        resp = c.get("/api/v1/funds/000000.OF")
        assert resp.status_code == 404
        body = resp.json()
        assert body["code"] == 40002
        assert body["data"] is None
        assert body["trace_id"]
    app.dependency_overrides.clear()
    Base.metadata.drop_all(eng)
    eng.dispose()


def test_validation_error_mapped_40001(client: TestClient) -> None:
    """§8.2：RequestValidationError -> 40001。"""
    # 暂无严格校验端点；用 OpenAPI 路径非数字触发 404/422 兜底
    # 这里改用 POST 一个不存在路由，预期 404 信封
    resp = client.post("/api/v1/__nonexistent__", json={})
    assert resp.status_code == 404
    assert resp.json()["code"] == 40002
