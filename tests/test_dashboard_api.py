"""仪表盘聚合接口单测(P1-12，详设§3.13 / DC-001 / FR-D1~D6)。

DB 集成：聚合视图四区 + Top10(ADR-002 只读 scores) + 信封 + 缓存命中。
标记 db，无 PG 跳过。
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

import infra.redis.cache as cache_mod
from infra.redis.cache import clear_memory_cache

pytestmark = pytest.mark.db


@pytest.fixture()
def client_with_scores(db_url: str):
    """建表 + 基金 + 评分 + 分红 + TestClient。"""
    from collections.abc import Iterator

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session, sessionmaker

    import infra.db.models  # noqa: F401
    from api.deps import get_db
    from infra.db import Base
    from infra.db.models import Fund, FundDividend, Score

    eng = create_engine(db_url)
    Base.metadata.drop_all(eng, checkfirst=True)
    Base.metadata.create_all(eng)
    TestSession = sessionmaker(bind=eng, autocommit=False, autoflush=False)
    with TestSession() as s:
        # 三只 mixed 基金 + 评分
        for i, code in enumerate(["000001.OF", "000002.OF", "000003.OF"]):
            s.add(
                Fund(
                    code=code,
                    name=f"基金{i + 1}",
                    type_="mixed",
                    launch_date=date.today() - timedelta(days=100 + i),
                    source="AkShare",
                    as_of=date.today(),
                )
            )
            s.add(
                Score(
                    code=code,
                    as_of=date.today(),
                    composite=Decimal(80 + i * 5),  # 80, 85, 90
                    weights={"ret": 20},
                    factors={"ret": float(80 + i * 5)},
                )
            )
        # 分红事件
        s.add(
            FundDividend(
                code="000001.OF",
                ex_date=date.today() - timedelta(days=5),
                div_per_unit=Decimal("0.15"),
                source="AkShare",
            )
        )
        s.commit()

    # 强制走进程内缓存(Redis 可能未连)
    cache_mod.get_redis = lambda: None  # type: ignore[assignment]
    clear_memory_cache()

    def _override_get_db() -> Iterator[Session]:
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    from api.main import create_app

    app = create_app()
    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    clear_memory_cache()
    Base.metadata.drop_all(eng)
    eng.dispose()


class TestDashboard:
    """GET /api/v1/dashboard(§3.13)。"""

    def test_dashboard_envelope(self, client_with_scores: TestClient) -> None:
        """七字段信封 + 四区齐全。"""
        resp = client_with_scores.get("/api/v1/dashboard")
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        assert body["data"] is not None
        data = body["data"]
        # 四区
        assert "portfolio_return" in data
        assert "top10" in data
        assert "dynamics" in data
        assert "learn_one" in data
        assert "todos" in data

    def test_top10_from_scores(self, client_with_scores: TestClient) -> None:
        """Top10 来自 scores 表(ADR-002 只读)，按 composite 降序。"""
        resp = client_with_scores.get("/api/v1/dashboard")
        top10 = resp.json()["data"]["top10"]
        assert len(top10) == 3
        # 降序：90, 85, 80
        scores = [t["score"] for t in top10]
        assert scores == sorted(scores, reverse=True)
        assert top10[0]["score"] == 90.0

    def test_dynamics_includes_dividend(self, client_with_scores: TestClient) -> None:
        """近期动态含分红事件。"""
        resp = client_with_scores.get("/api/v1/dashboard")
        dynamics = resp.json()["data"]["dynamics"]
        divs = [d for d in dynamics if d["type"] == "dividend"]
        assert len(divs) >= 1
        assert "000001.OF" in divs[0]["title"]

    def test_learn_one_returns_top_fund(self, client_with_scores: TestClient) -> None:
        """学一基取评分最高的基金。"""
        resp = client_with_scores.get("/api/v1/dashboard")
        learn = resp.json()["data"]["learn_one"]
        assert learn["available"] is True
        assert learn["score"] == 90.0
        assert "glossary_links" in learn

    def test_cache_hit_returns_source_cache(self, client_with_scores: TestClient) -> None:
        """二次请求命中缓存 -> source=cache(§3.13.5)。"""
        client_with_scores.get("/api/v1/dashboard")  # 首次写缓存
        resp = client_with_scores.get("/api/v1/dashboard")  # 二次命中
        assert resp.json()["source"] == "cache"

    def test_first_request_source_batch(self, client_with_scores: TestClient) -> None:
        """首次请求 source=batch。"""
        clear_memory_cache()
        resp = client_with_scores.get("/api/v1/dashboard")
        assert resp.json()["source"] == "batch"
