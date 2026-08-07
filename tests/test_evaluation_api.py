"""评估接口集成测试(P1-04a，§3.3.6 / §2.21 / §3.3.7 溯源)。

DB 集成：写入基金+净值，调端点验证信封(7字段) + 指标/cv_flag + 40002 基金不存在。
标记 db，无 PG 跳过。
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

pytestmark = pytest.mark.db


@pytest.fixture()
def client_with_fund(db_session: Session) -> Iterator[TestClient]:
    """种子数据 + TestClient(get_db override 指向共享引擎；表已由 conftest db_session truncate)。"""
    from sqlalchemy.orm import sessionmaker

    from api.deps import get_db
    from infra.db.models import Fund, Nav, Score

    # conftest db_session 已 truncate 清表；复用其引擎建 TestSession(请求期隔离)
    TestSession = sessionmaker(bind=db_session.bind, autocommit=False, autoflush=False)
    with TestSession() as s:
        s.add(
            Fund(
                code="000001",
                name="华夏成长混合",
                type_="mixed",
                source="AkShare",
                as_of=date.today(),
            )
        )
        # 生成 252 天净值(稳定上涨,年化约10%)
        base = date(2024, 1, 1)
        for i in range(252):
            nav_val = Decimal("1.0") * (Decimal("1.10") ** (Decimal(str(i)) / Decimal("250")))
            s.add(
                Nav(
                    code="000001",
                    trade_date=base + timedelta(days=i),
                    nav=nav_val,
                    acc_nav=nav_val * 2,
                    adj_nav=nav_val,
                    is_estimate=False,
                    source="AkShare",
                    as_of=date.today(),
                )
            )
        # 写入批算评分(模拟 P1-05 夜算产出，含子分供在线查询/调权重重算)
        s.add(
            Score(
                code="000001",
                window="3y",
                weights={"ret": 20, "risk": 25, "perf": 20, "scale": 15, "manager": 20},
                composite=Decimal("82.3"),
                factors={
                    "ret": {"sub_score": 88.0, "weight": 20, "raw": 0.10, "contrib": 1760.0},
                    "risk": {"sub_score": 75.0, "weight": 25, "raw": -0.05, "contrib": 1875.0},
                    "perf": {"sub_score": 80.0, "weight": 20, "raw": 0.8, "contrib": 1600.0},
                    "scale": {"sub_score": 100.0, "weight": 15, "raw": 100.0, "contrib": 1500.0},
                    "manager": {"sub_score": 70.0, "weight": 20, "raw": 0.02, "contrib": 1400.0},
                },
                as_of=date.today(),
            )
        )
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


class TestMetricsEndpoint:
    """GET /api/v1/funds/{code}/metrics(§3.3.2)。"""

    def test_returns_envelope(self, client_with_fund: TestClient) -> None:
        """§2.21 七字段信封 + 指标(§3.3.7 source/as_of)。"""
        resp = client_with_fund.get("/api/v1/funds/000001/metrics?window=3Y")
        assert resp.status_code == 200
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
        assert body["code"] == 0
        data = body["data"]
        assert data["annualized_return"] is not None
        assert data["max_drawdown"] is not None
        assert data["cv_flag"] is not None
        assert body["source"] == "batch"
        assert body["as_of"] is not None

    def test_fund_not_found_40002(self, client_with_fund: TestClient) -> None:
        """§4.2 基金不存在 -> 40002。"""
        resp = client_with_fund.get("/api/v1/funds/999999/metrics")
        assert resp.status_code == 404
        assert resp.json()["code"] == 40002


class TestScoreEndpoint:
    """GET /api/v1/funds/{code}/score(§3.3.8.1, 唯一权威源)。"""

    def test_returns_score_envelope(self, client_with_fund: TestClient) -> None:
        """五因子评分信封。"""
        resp = client_with_fund.get("/api/v1/funds/000001/score")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "composite" in data
        assert "factors" in data
        assert "weights" in data
        # 权重默认 SCORE_WEIGHTS(E4/E5: ret=20)
        assert data["weights"]["ret"] == 20
        # composite 来自批算 scores 表(ADR-002)，非 None
        assert data["composite"] is not None

    def test_custom_weights(self, client_with_fund: TestClient) -> None:
        """可调权重(ADR-002, ?weights=)。"""
        resp = client_with_fund.get("/api/v1/funds/000001/score?weights=50:25:20:15:20")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["weights"]["ret"] == 50  # 调权生效

    def test_fund_not_found_40002(self, client_with_fund: TestClient) -> None:
        resp = client_with_fund.get("/api/v1/funds/999999/score")
        assert resp.status_code == 404
        assert resp.json()["code"] == 40002

    def test_stale_cache_schema_drift_not_50302(self, client_with_fund: TestClient) -> None:
        """缓存 schema 漂移(旧版本残留缺 weights/as_of) -> 视为未命中走 DB，不 50302。

        回归：旧缓存含 brinson/scope 等历史字段而缺 weights，``cached["weights"]``
        曾抛 KeyError 被 get_db 吞成 50302；修复后应降级为未命中、走 DB 重算并自愈覆写。
        """
        from infra.redis.cache import cache_set

        cache_set(
            "score",
            code="000001",
            value={
                "code": "000001",
                "composite": 82.3,
                "factors": {
                    "ret": {"sub_score": 88.0, "weight": 20, "raw": 0.10, "contrib": 1760.0},
                },
                # 旧 schema 字段(无 weights/as_of)
                "brinson": None,
                "scope": "mixed",
                "universe_tag": "cross_section",
            },
        )
        resp = client_with_fund.get("/api/v1/funds/000001/score")
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0  # 非 50302(数据库不可用)
        assert body["data"]["composite"] is not None
        assert body["data"]["weights"]["ret"] == 20  # 走 DB 重算，权重默认


class TestStyleboxEndpoint:
    """GET /api/v1/funds/{code}/stylebox(§3.3.1, E13)。"""

    def test_equity_type_returns(self, client_with_fund: TestClient) -> None:
        """权益类(mixed) -> 风格箱算法已实现；fixture 无持仓基本面 -> available=False。"""
        resp = client_with_fund.get("/api/v1/funds/000001/stylebox")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "size" in data
        assert "value_growth" in data
        assert data["available"] is False  # 持仓基本面缺失(P1-02 采集后补)
        assert data["method"] == "holdings_missing"
        assert data["reg_window"] == "3y"  # E13 披露

    def test_fund_not_found_40002(self, client_with_fund: TestClient) -> None:
        resp = client_with_fund.get("/api/v1/funds/999999/stylebox")
        assert resp.status_code == 404
        assert resp.json()["code"] == 40002


class TestAttributionEndpoint:
    """GET /api/v1/funds/{code}/attribution(§3.3.8.2)。"""

    def test_returns_envelope(self, client_with_fund: TestClient) -> None:
        """Brinson 归因信封(混合基 scope=mixed)。"""
        resp = client_with_fund.get("/api/v1/funds/000001/attribution")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "scope" in data
        assert data["scope"] == "mixed"  # 混合基在 BRINSON_SCOPE
        # 基准收益缺失(MVP) -> unavailable=True，不返回误导性 0 值(§3.3.8.2)
        assert data["unavailable"] is True
        assert data["active_return"] is None  # 不返回假 0

    def test_fund_not_found_40002(self, client_with_fund: TestClient) -> None:
        resp = client_with_fund.get("/api/v1/funds/999999/attribution")
        assert resp.status_code == 404
        assert resp.json()["code"] == 40002


class TestResearchEndpoint:
    """GET /api/v1/funds/{code}/research(§3.3.7, PEG/ERP 代理)。"""

    def test_returns_cards(self, client_with_fund: TestClient) -> None:
        """研究卡片(PEG/ERP 代理标注)。"""
        resp = client_with_fund.get("/api/v1/funds/000001/research")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "peg" in data
        assert "erp" in data
        assert "cards" in data
        assert len(data["cards"]) >= 2  # 至少 PEG + ERP 卡
        # 卡片 name 带"(代理)"(PEG/ERP)
        names = [c["name"] for c in data["cards"]]
        assert any("(代理)" in n for n in names)

    def test_fund_not_found_40002(self, client_with_fund: TestClient) -> None:
        resp = client_with_fund.get("/api/v1/funds/999999/research")
        assert resp.status_code == 404
        assert resp.json()["code"] == 40002
