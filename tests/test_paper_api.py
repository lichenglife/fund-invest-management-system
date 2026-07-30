"""模拟交易单测(P1-07a，§3.5 / DC-005 / §8.4 事务原子性)。

DB 集成：买入/卖出/持仓看板/重置；验证现金持仓一致、40003 业务冲突。
标记 db，无 PG 跳过。
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.db


@pytest.fixture()
def client_with_account(db_url: str):
    """建表 + 基金+净值 + 返回 TestClient。"""
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
                code="000001", name="华夏成长", type_="mixed", source="AkShare", as_of=date.today()
            )
        )
        base = date(2025, 1, 1)
        for i in range(30):
            nav_val = Decimal("1.0") + Decimal(str(i)) * Decimal("0.001")
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


class TestBuy:
    """POST /api/v1/paper/buy(§3.5.6)。"""

    def test_buy_by_amount(self, client_with_account: TestClient) -> None:
        """按金额买入：扣现金 + 增持仓 + 记流水。"""
        resp = client_with_account.post(
            "/api/v1/paper/buy",
            json={
                "code": "000001",
                "amount": "10000",
                "trade_date": "2025-01-15",
            },
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["trade_id"] > 0
        assert data["position"]["code"] == "000001"
        assert data["position"]["shares"] > 0
        assert data["cash"] < 1000000  # 现金减少
        assert data["cash"] == pytest.approx(1000000 - data["position"]["shares"] * 1.014, abs=0.01)

    def test_buy_by_shares(self, client_with_account: TestClient) -> None:
        """按份额买入。"""
        resp = client_with_account.post(
            "/api/v1/paper/buy",
            json={
                "code": "000001",
                "shares": "1000",
                "trade_date": "2025-01-15",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["position"]["shares"] == pytest.approx(1000)
        assert resp.json()["data"]["cash"] == pytest.approx(1000000 - 1000 * 1.014, abs=0.01)

    def test_buy_invalid_no_amount_no_shares(self, client_with_account: TestClient) -> None:
        """amount/shares 均空 -> 40001(参数)。"""
        resp = client_with_account.post("/api/v1/paper/buy", json={"code": "000001"})
        assert resp.status_code == 400
        assert resp.json()["code"] == 40001

    def test_buy_insufficient_cash(self, client_with_account: TestClient) -> None:
        """现金不足 -> 40003(业务冲突)。"""
        resp = client_with_account.post(
            "/api/v1/paper/buy",
            json={
                "code": "000001",
                "amount": "99999999",
                "trade_date": "2025-01-15",
            },
        )
        assert resp.status_code == 409
        assert resp.json()["code"] == 40003

    def test_buy_fund_not_found(self, client_with_account: TestClient) -> None:
        """基金不存在 -> 40002。"""
        resp = client_with_account.post(
            "/api/v1/paper/buy",
            json={
                "code": "999999",
                "amount": "1000",
                "trade_date": "2025-01-15",
            },
        )
        assert resp.status_code == 404
        assert resp.json()["code"] == 40002


class TestSell:
    """POST /api/v1/paper/sell(§3.5.6)。"""

    def test_sell_after_buy(self, client_with_account: TestClient) -> None:
        """买入后卖出：增持现金 + 减持仓。"""
        # 先买
        client_with_account.post(
            "/api/v1/paper/buy",
            json={
                "code": "000001",
                "shares": "1000",
                "trade_date": "2025-01-15",
            },
        )
        # 卖
        resp = client_with_account.post(
            "/api/v1/paper/sell",
            json={
                "code": "000001",
                "shares": "500",
                "trade_date": "2025-01-20",
            },
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["position"]["shares"] == pytest.approx(500)  # 1000-500
        assert data["cash"] > 1000000 - 1000 * 1.014  # 卖出后现金增加

    def test_sell_no_position(self, client_with_account: TestClient) -> None:
        """无持仓 -> 40002。"""
        resp = client_with_account.post(
            "/api/v1/paper/sell",
            json={
                "code": "000001",
                "shares": "100",
                "trade_date": "2025-01-15",
            },
        )
        assert resp.status_code == 404
        assert resp.json()["code"] == 40002

    def test_sell_insufficient_shares(self, client_with_account: TestClient) -> None:
        """份额不足 -> 40003。"""
        client_with_account.post(
            "/api/v1/paper/buy",
            json={
                "code": "000001",
                "shares": "100",
                "trade_date": "2025-01-15",
            },
        )
        resp = client_with_account.post(
            "/api/v1/paper/sell",
            json={
                "code": "000001",
                "shares": "200",
                "trade_date": "2025-01-20",
            },
        )
        assert resp.status_code == 409
        assert resp.json()["code"] == 40003


class TestPortfolio:
    """GET /api/v1/paper/portfolio(§3.5.3)。"""

    def test_empty_portfolio(self, client_with_account: TestClient) -> None:
        """空账户：现金=100万，无持仓。"""
        resp = client_with_account.get("/api/v1/paper/portfolio")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["cash"] == 1000000
        assert data["init_capital"] == 1000000
        assert data["positions"] == []
        assert data["total_assets"] == 1000000

    def test_portfolio_after_buy(self, client_with_account: TestClient) -> None:
        """买入后：持仓明细 + 总资产。"""
        client_with_account.post(
            "/api/v1/paper/buy",
            json={
                "code": "000001",
                "shares": "1000",
                "trade_date": "2025-01-15",
            },
        )
        resp = client_with_account.get("/api/v1/paper/portfolio")
        data = resp.json()["data"]
        assert len(data["positions"]) == 1
        assert data["positions"][0]["code"] == "000001"
        assert data["positions"][0]["shares"] == pytest.approx(1000)
        assert data["total_market_value"] > 0


class TestReset:
    """POST /api/v1/paper/reset(§3.5.7 二次确认)。"""

    def test_reset_without_confirm(self, client_with_account: TestClient) -> None:
        """未确认 -> 40003。"""
        resp = client_with_account.post("/api/v1/paper/reset", json={"confirm": False})
        assert resp.status_code == 409
        assert resp.json()["code"] == 40003

    def test_reset_with_confirm(self, client_with_account: TestClient) -> None:
        """确认重置：清仓 + 现金回100万。"""
        # 先买
        client_with_account.post(
            "/api/v1/paper/buy",
            json={
                "code": "000001",
                "shares": "1000",
                "trade_date": "2025-01-15",
            },
        )
        # 重置
        resp = client_with_account.post("/api/v1/paper/reset", json={"confirm": True})
        assert resp.status_code == 200
        # 验证
        portfolio = client_with_account.get("/api/v1/paper/portfolio").json()["data"]
        assert portfolio["cash"] == 1000000  # 现金回初始
        assert portfolio["positions"] == []  # 持仓清空


class TestAtomicity:
    """§8.4 事务原子性：现金/持仓一致。"""

    def test_cash_position_consistent(self, client_with_account: TestClient) -> None:
        """买卖后现金+持仓市值 = 总资产(守恒)。"""
        client_with_account.post(
            "/api/v1/paper/buy",
            json={
                "code": "000001",
                "shares": "1000",
                "trade_date": "2025-01-15",
            },
        )
        client_with_account.post(
            "/api/v1/paper/sell",
            json={
                "code": "000001",
                "shares": "300",
                "trade_date": "2025-01-20",
            },
        )
        data = client_with_account.get("/api/v1/paper/portfolio").json()["data"]
        # 守恒：现金 + 持仓市值 = 总资产
        assert data["cash"] + data["total_market_value"] == pytest.approx(
            data["total_assets"], abs=0.01
        )


class TestDividend:
    """POST /api/paper/dividend 分红复权(§3.5.4 / E3)。"""

    def test_reinvest_increases_shares(self, client_with_account: TestClient) -> None:
        """再投：持仓份额增加。"""
        # 先买 1000 份
        client_with_account.post(
            "/api/v1/paper/buy",
            json={
                "code": "000001",
                "shares": "1000",
                "trade_date": "2025-01-15",
            },
        )
        # 分红：每份 0.1，除息净值 1.0 -> 新增 100 份
        resp = client_with_account.post(
            "/api/v1/paper/dividend",
            json={
                "code": "000001",
                "div_per_unit": "0.1",
                "ex_nav": "1.0",
                "mode": "reinvest",
            },
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["shares_after"] == pytest.approx(1100)
        assert data["new_shares"] == pytest.approx(100)

    def test_cash_dividend_increases_cash(self, client_with_account: TestClient) -> None:
        """现金分红：份额不变，现金增加。"""
        client_with_account.post(
            "/api/v1/paper/buy",
            json={
                "code": "000001",
                "shares": "1000",
                "trade_date": "2025-01-15",
            },
        )
        cash_before = client_with_account.get("/api/v1/paper/portfolio").json()["data"]["cash"]
        resp = client_with_account.post(
            "/api/v1/paper/dividend",
            json={
                "code": "000001",
                "div_per_unit": "0.1",
                "ex_nav": "1.0",
                "mode": "cash",
            },
        )
        assert resp.status_code == 200
        cash_after = client_with_account.get("/api/v1/paper/portfolio").json()["data"]["cash"]
        assert cash_after > cash_before  # 现金增加

    def test_dividend_no_position(self, client_with_account: TestClient) -> None:
        """无持仓 -> 40002。"""
        resp = client_with_account.post(
            "/api/v1/paper/dividend",
            json={
                "code": "000001",
                "div_per_unit": "0.1",
                "ex_nav": "1.0",
            },
        )
        assert resp.status_code == 404
        assert resp.json()["code"] == 40002


class TestSellRedeemFee:
    """E3 赎回费(DB 集成)。"""

    def test_sell_returns_redeem_fee(self, client_with_account: TestClient) -> None:
        """卖出返回赎回费字段(E3)。"""
        client_with_account.post(
            "/api/v1/paper/buy",
            json={
                "code": "000001",
                "shares": "1000",
                "trade_date": "2025-01-15",
            },
        )
        resp = client_with_account.post(
            "/api/v1/paper/sell",
            json={
                "code": "000001",
                "shares": "500",
                "trade_date": "2025-01-20",
            },
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "redeem_fee" in data  # 赎回费字段
        assert "settled_amount" in data  # 扣费后到账
