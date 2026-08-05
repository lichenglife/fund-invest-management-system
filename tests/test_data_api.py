"""数据中心接口单测(P1-02a/b，详设§3.2 / §2.21 契约)。

DB 集成：检索/分类树/档案/净值/持仓/下载/字段解释/降级路径；40002 不存在。
标记 db，无 PG 跳过。
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.db


@pytest.fixture()
def client_with_data(db_url: str):
    """建表 + 基金/净值/持仓/评分 + 返回 TestClient。"""
    from collections.abc import Iterator

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session, sessionmaker

    import infra.db.models  # noqa: F401
    from api.deps import get_db
    from infra.db import Base
    from infra.db.models import Fund, Holding, Nav, Score

    eng = create_engine(db_url)
    Base.metadata.drop_all(eng, checkfirst=True)
    Base.metadata.create_all(eng)
    TestSession = sessionmaker(bind=eng, autocommit=False, autoflush=False)
    with TestSession() as s:
        # 基金
        s.add(
            Fund(
                code="000001.OF",
                name="华夏成长",
                type_="mixed",
                sub_type="偏股混合",
                theme="成长",
                style="大盘成长",
                source="AkShare",
                as_of=date.today(),
            )
        )
        s.add(
            Fund(
                code="000002.OF",
                name="华夏大盘",
                type_="stock",
                sub_type="股票型",
                theme="宽基",
                source="AkShare",
                as_of=date.today(),
            )
        )
        # 净值(最近 3 天)
        for i in range(3):
            d = date.today() - timedelta(days=i)
            s.add(
                Nav(
                    code="000001.OF",
                    trade_date=d,
                    nav=Decimal("1.0") + Decimal(i) * Decimal("0.01"),
                    acc_nav=Decimal("1.1") + Decimal(i) * Decimal("0.01"),
                    adj_nav=Decimal("1.2") + Decimal(i) * Decimal("0.01"),
                    is_estimate=False,
                    source="AkShare",
                    as_of=date.today(),
                )
            )
        # 持仓
        s.add(
            Holding(
                code="000001.OF",
                report_date=date.today(),
                stock_code="600519.SH",
                stock_name="贵州茅台",
                weight=Decimal("0.08"),
                source="AkShare",
                as_of=date.today(),
            )
        )
        # 评分(ADR-002 唯一权威源)
        s.add(
            Score(
                code="000001.OF",
                as_of=date.today(),
                composite=Decimal("82.5"),
                weights={"ret": 20},
                factors={"ret": 80.0},
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


class TestSearchFunds:
    """GET /api/v1/funds(§3.2.2)。"""

    def test_list_default(self, client_with_data: TestClient) -> None:
        """默认列表 + 七字段信封。"""
        resp = client_with_data.get("/api/v1/funds")
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        assert body["data"]["total"] >= 2
        items = body["data"]["items"]
        assert items[0]["code"].startswith("000001") or items[0]["code"].startswith("000002")

    def test_search_by_query(self, client_with_data: TestClient) -> None:
        """名称模糊匹配。"""
        resp = client_with_data.get("/api/v1/funds", params={"q": "成长"})
        assert resp.status_code == 200
        items = resp.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["name"] == "华夏成长"

    def test_filter_by_type(self, client_with_data: TestClient) -> None:
        """类型过滤。"""
        resp = client_with_data.get("/api/v1/funds", params={"type": "stock"})
        assert resp.status_code == 200
        items = resp.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["type"] == "stock"


class TestFundTree:
    """GET /api/v1/funds/tree(§3.2.2)。"""

    def test_tree_structure(self, client_with_data: TestClient) -> None:
        resp = client_with_data.get("/api/v1/funds/tree")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "mixed" in data["types"] and "stock" in data["types"]
        assert len(data["tree"]) >= 2


class TestFundProfile:
    """GET /api/v1/funds/{code}(§3.2.2)。"""

    def test_profile_with_score_and_nav(self, client_with_data: TestClient) -> None:
        """档案含最新净值 + 评分(ADR-002 只读)。"""
        resp = client_with_data.get("/api/v1/funds/000001.OF")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["name"] == "华夏成长"
        assert data["nav"] is not None
        assert data["score"] == pytest.approx(82.5)
        # managers 表未建(D2) -> 降级 None
        assert data["manager"] is None

    def test_profile_not_found(self, client_with_data: TestClient) -> None:
        """不存在 -> 40002。"""
        resp = client_with_data.get("/api/v1/funds/999999.OF")
        assert resp.status_code == 404
        assert resp.json()["code"] == 40002


class TestNavSeries:
    """GET /api/v1/funds/{code}/nav(§3.2.2)。"""

    def test_nav_returns_three_columns(self, client_with_data: TestClient) -> None:
        """净值序列含 nav/acc_nav/adj_nav 三列。"""
        resp = client_with_data.get("/api/v1/funds/000001.OF/nav?days=10")
        assert resp.status_code == 200
        series = resp.json()["data"]
        assert len(series) == 3
        assert {"date", "nav", "acc_nav", "adj_nav", "is_estimate"} <= set(series[0])

    def test_nav_not_found(self, client_with_data: TestClient) -> None:
        resp = client_with_data.get("/api/v1/funds/999999.OF/nav")
        assert resp.status_code == 404
        assert resp.json()["code"] == 40002


class TestHoldings:
    """GET /api/v1/funds/{code}/holdings(§3.2.2)。"""

    def test_holdings_returns_top10(self, client_with_data: TestClient) -> None:
        resp = client_with_data.get("/api/v1/funds/000001.OF/holdings")
        assert resp.status_code == 200
        holdings = resp.json()["data"]
        assert len(holdings) == 1
        assert holdings[0]["stock_name"] == "贵州茅台"


class TestIntradayDegraded:
    """GET /api/v1/funds/{code}/intraday(§3.2.7 降级)。"""

    def test_intraday_degrades_to_latest(self, client_with_data: TestClient) -> None:
        """盘中表未建 -> 降级为最新净值 + is_estimate=True。"""
        resp = client_with_data.get("/api/v1/funds/000001.OF/intraday")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["is_estimate"] is True
        assert data["available"] is True


class TestManagerDegraded:
    """GET /api/v1/funds/{code}/manager(D2 降级 50301)。"""

    def test_manager_returns_50301(self, client_with_data: TestClient) -> None:
        """managers 表未建 -> 50301(§2.15 降级)。"""
        resp = client_with_data.get("/api/v1/funds/000001.OF/manager")
        assert resp.status_code == 503
        assert resp.json()["code"] == 50301

    def test_manager_fund_not_found(self, client_with_data: TestClient) -> None:
        """基金不存在 -> 40002(优先于 50301)。"""
        resp = client_with_data.get("/api/v1/funds/999999.OF/manager")
        assert resp.status_code == 404
        assert resp.json()["code"] == 40002


class TestFieldGlossary:
    """GET /api/v1/fields/{name}(D2 内置词典)。"""

    def test_known_field(self, client_with_data: TestClient) -> None:
        resp = client_with_data.get("/api/v1/fields/adj_nav")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["field"] == "adj_nav"
        assert "后复权" in data["description"]

    def test_unknown_field_50301(self, client_with_data: TestClient) -> None:
        resp = client_with_data.get("/api/v1/fields/bogus_field")
        assert resp.status_code == 503
        assert resp.json()["code"] == 50301


class TestDownloadNav:
    """GET /api/v1/funds/{code}/download(§3.2.7 CSV)。"""

    def test_download_csv(self, client_with_data: TestClient) -> None:
        """CSV 下载 + 文件头含 source/as_of。"""
        resp = client_with_data.get("/api/v1/funds/000001.OF/download?days=10")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]
        body = resp.text
        assert body.startswith("# source=FundLens")
        assert "as_of=" in body
        assert "date,nav,acc_nav,adj_nav" in body
