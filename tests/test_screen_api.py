"""筛选器单测(P1-06a，详设§3.4.6 / §2.21.2 / DC-004)。

DB 集成：写入基金+评分，调端点验证过滤/排序/分页/信封。标记 db。
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

pytestmark = pytest.mark.db


@pytest.fixture()
def client_with_funds(db_session: Session):
    """种子数据 + TestClient(get_db override 指向共享引擎；表已由 conftest db_session truncate)。"""
    from collections.abc import Iterator

    from sqlalchemy.orm import sessionmaker

    from api.deps import get_db
    from infra.db.models import Fund, Score

    # conftest db_session 已 truncate 清表；复用其引擎建 TestSession(请求期隔离)
    TestSession = sessionmaker(bind=db_session.bind, autocommit=False, autoflush=False)
    with TestSession() as s:
        funds = [
            Fund(
                code="000001", name="华夏成长", type_="mixed", source="AkShare", as_of=date.today()
            ),
            Fund(
                code="000002", name="华夏大盘", type_="mixed", source="AkShare", as_of=date.today()
            ),
            Fund(
                code="000003",
                name="易方达蓝筹",
                type_="stock",
                source="AkShare",
                as_of=date.today(),
            ),
            Fund(
                code="000004", name="招商债券", type_="bond", source="AkShare", as_of=date.today()
            ),
            Fund(
                code="000005", name="兴全趋势", type_="mixed", source="AkShare", as_of=date.today()
            ),
        ]
        s.add_all(funds)
        s.commit()
        scores = [
            Score(
                code="000001", weights={}, composite=Decimal("85.0"), factors={}, as_of=date.today()
            ),
            Score(
                code="000002", weights={}, composite=Decimal("82.0"), factors={}, as_of=date.today()
            ),
            Score(
                code="000003", weights={}, composite=Decimal("78.0"), factors={}, as_of=date.today()
            ),
            Score(
                code="000005", weights={}, composite=Decimal("90.0"), factors={}, as_of=date.today()
            ),
        ]
        s.add_all(scores)
        s.commit()

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


class TestScreenEndpoint:
    """POST /api/v1/screen(§3.4.6)。"""

    def test_no_filter_returns_all(self, client_with_funds: TestClient) -> None:
        """无条件 -> 返回全部(§2.21 {items,total})。"""
        resp = client_with_funds.post("/api/v1/screen", json={})
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        assert body["data"]["total"] == 5
        assert len(body["data"]["items"]) == 5

    def test_filter_by_type(self, client_with_funds: TestClient) -> None:
        """按类型过滤(type in [mixed])。"""
        resp = client_with_funds.post(
            "/api/v1/screen",
            json={
                "filters": [{"field": "type", "op": "in", "value": ["mixed"]}],
            },
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 3  # 000001/000002/000005
        assert all(i["type"] == "mixed" for i in data["items"])

    def test_filter_by_score_gte(self, client_with_funds: TestClient) -> None:
        """评分过滤(score >= 85)。"""
        resp = client_with_funds.post(
            "/api/v1/screen",
            json={
                "filters": [{"field": "score", "op": ">=", "value": 85}],
            },
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        # 000001(85)/000005(90)；000004 无评分(LEFT JOIN NULL)
        codes = {i["code"] for i in data["items"]}
        assert "000001" in codes
        assert "000005" in codes

    def test_sort_by_score_desc(self, client_with_funds: TestClient) -> None:
        """按 composite 降序(§2.21.2 默认)。"""
        resp = client_with_funds.post(
            "/api/v1/screen",
            json={
                "sort": "composite",
                "order": "desc",
            },
        )
        assert resp.status_code == 200
        items = resp.json()["data"]["items"]
        scores = [i["score"] for i in items if i["score"] is not None]
        assert scores == sorted(scores, reverse=True)  # 降序

    def test_pagination(self, client_with_funds: TestClient) -> None:
        """分页(§2.21.2 page/page_size)。"""
        resp = client_with_funds.post(
            "/api/v1/screen",
            json={
                "page": 1,
                "page_size": 2,
            },
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 5
        assert len(data["items"]) == 2
        # 第2页
        resp2 = client_with_funds.post(
            "/api/v1/screen",
            json={
                "page": 2,
                "page_size": 2,
            },
        )
        assert len(resp2.json()["data"]["items"]) == 2

    def test_envelope_seven_fields(self, client_with_funds: TestClient) -> None:
        """§2.21 七字段信封。"""
        resp = client_with_funds.post("/api/v1/screen", json={})
        body = resp.json()
        assert set(body.keys()) == {
            "code",
            "data",
            "source",
            "as_of",
            "disclaimer",
            "message",
            "trace_id",
        }

    def test_name_like_filter(self, client_with_funds: TestClient) -> None:
        """名称模糊过滤(like)。"""
        resp = client_with_funds.post(
            "/api/v1/screen",
            json={
                "filters": [{"field": "name", "op": "like", "value": "%华夏%"}],
            },
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 2  # 华夏成长/华夏大盘


class TestScreenDedupEndpoint:
    """GET /api/v1/screen/dedup(§3.4.7, 重叠>=70%)。"""

    def test_dedup_no_holdings(self, client_with_funds: TestClient) -> None:
        """无持仓数据 -> available=False。"""
        resp = client_with_funds.get("/api/v1/screen/dedup?codes=000001,000002")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["available"] is False  # 无持仓
        assert data["similar_count"] == 0
