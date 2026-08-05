"""单基深度实验室接口单测(P1-09b，详设§3.8 / DC-011 / FR-40~42)。

DB 集成：回本/情景/策略三接口 + 信封 + 40002；输入收益率来自真实净值(§3.8.6)。
标记 db，无 PG 跳过。
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.db


@pytest.fixture()
def client_with_fund_nav(db_url: str):
    """建表 + 基金 + 净值(先涨后跌，触发回本测算) + TestClient。"""
    from collections.abc import Iterator

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session, sessionmaker

    import infra.db.models  # noqa: F401
    from api.deps import get_db
    from infra.db import Base
    from infra.db.models import Fund, Nav

    eng = create_engine(db_url)
    Base.metadata.drop_all(eng, checkfirst=True)
    Base.metadata.create_all(eng)
    TestSession = sessionmaker(bind=eng, autocommit=False, autoflush=False)
    with TestSession() as s:
        s.add(
            Fund(
                code="000001.OF",
                name="华夏成长",
                type_="mixed",
                source="AkShare",
                as_of=date.today(),
            )
        )
        # 净值：前 20 日涨，后 20 日跌(末日低于首日 -> 负收益，触发回本)
        for i in range(40):
            d = date.today() - timedelta(days=40 - i)
            if i < 20:
                nav_val = Decimal("1.0") + Decimal(i) * Decimal("0.01")  # 涨至 1.19
            else:
                nav_val = Decimal("1.19") - Decimal(i - 20) * Decimal("0.02")  # 跌回 0.81
            s.add(
                Nav(
                    code="000001.OF",
                    trade_date=d,
                    nav=nav_val,
                    acc_nav=nav_val,
                    adj_nav=nav_val,
                    is_estimate=False,
                    source="AkShare",
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
    Base.metadata.drop_all(eng)
    eng.dispose()


class TestBreakevenEndpoint:
    """GET /api/v1/funds/{code}/breakeven(§3.8.2)。"""

    def test_breakeven_envelope(self, client_with_fund_nav: TestClient) -> None:
        """回本测算：负收益 -> 回本需涨 + 三情景月数。"""
        resp = client_with_fund_nav.get("/api/v1/funds/000001.OF/breakeven")
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        data = body["data"]
        assert data["code"] == "000001.OF"
        assert data["profitable"] is False  # 末日净值低于首日
        assert data["breakeven_gain_pct"] is not None and data["breakeven_gain_pct"] > 0
        assert "optimistic" in data["months_to_breakeven"]

    def test_breakeven_not_found(self, client_with_fund_nav: TestClient) -> None:
        """基金不存在 -> 40002。"""
        resp = client_with_fund_nav.get("/api/v1/funds/999999.OF/breakeven")
        assert resp.status_code == 404
        assert resp.json()["code"] == 40002


class TestScenariosEndpoint:
    """GET /api/v1/funds/{code}/scenarios(§3.8.2)。"""

    def test_scenarios_three_curves(self, client_with_fund_nav: TestClient) -> None:
        """三情景投影曲线。"""
        resp = client_with_fund_nav.get("/api/v1/funds/000001.OF/scenarios?months=6")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert set(data["projections"]) == {"conservative", "baseline", "optimistic"}
        assert len(data["projections"]["baseline"]) == 7  # months+1

    def test_scenarios_not_found(self, client_with_fund_nav: TestClient) -> None:
        resp = client_with_fund_nav.get("/api/v1/funds/999999.OF/scenarios")
        assert resp.status_code == 404


class TestStrategiesEndpoint:
    """GET /api/v1/funds/{code}/strategies(§3.8.2)。"""

    def test_strategies_five(self, client_with_fund_nav: TestClient) -> None:
        """五策略对照。"""
        resp = client_with_fund_nav.get("/api/v1/funds/000001.OF/strategies")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 5
        strategies = [d["strategy"] for d in data]
        assert set(strategies) == {"hold", "dca", "swing", "rebalance", "stop_loss"}
        for d in data:
            assert "total_return" in d
            assert "max_drawdown" in d

    def test_strategies_not_found(self, client_with_fund_nav: TestClient) -> None:
        resp = client_with_fund_nav.get("/api/v1/funds/999999.OF/strategies")
        assert resp.status_code == 404
