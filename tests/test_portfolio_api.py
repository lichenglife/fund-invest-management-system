"""组合配置接口单测(P1-08a，§3.6 / DC-006)。

DB 集成：创建/查询/列表/删除/导入模拟持仓；40002 不存在。
标记 db，无 PG 跳过。
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.db


@pytest.fixture()
def client_with_funds(db_url: str):
    """建表 + 基金+模拟持仓 + 返回 TestClient。"""
    from collections.abc import Iterator

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session, sessionmaker

    import infra.db.models  # noqa: F401
    from api.deps import get_db
    from infra.db import Base
    from infra.db.models import Fund, PaperAccount, PaperPosition

    eng = create_engine(db_url)
    Base.metadata.drop_all(eng, checkfirst=True)
    Base.metadata.create_all(eng)
    TestSession = sessionmaker(bind=eng, autocommit=False, autoflush=False)
    with TestSession() as s:
        # 基金
        for code in ["000001", "000002", "000003"]:
            s.add(
                Fund(
                    code=code,
                    name=f"基金{code}",
                    type_="mixed",
                    source="AkShare",
                    as_of=date.today(),
                )
            )
        s.commit()
        # 模拟账户 + 持仓(供导入测试)
        s.add(
            PaperAccount(
                account_id="default", init_capital=Decimal("1000000"), cash=Decimal("500000")
            )
        )
        s.add(
            PaperPosition(
                account_id="default", code="000001", shares=Decimal("1000"), cost=Decimal("1.0")
            )
        )
        s.add(
            PaperPosition(
                account_id="default", code="000002", shares=Decimal("500"), cost=Decimal("2.0")
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


class TestCreatePortfolio:
    """POST /api/v1/portfolios(§3.6.5)。"""

    def test_create_manual(self, client_with_funds: TestClient) -> None:
        """手动创建组合 + 权重。"""
        resp = client_with_funds.post(
            "/api/v1/portfolios",
            json={
                "name": "我的组合",
                "source": "manual",
                "weights": [
                    {"code": "000001", "weight": 0.6},
                    {"code": "000002", "weight": 0.4},
                ],
            },
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["name"] == "我的组合"
        assert data["source"] == "manual"
        assert len(data["weights"]) == 2

    def test_create_invalid_source(self, client_with_funds: TestClient) -> None:
        """非法 source -> 40001。"""
        resp = client_with_funds.post(
            "/api/v1/portfolios",
            json={
                "source": "bogus",
            },
        )
        assert resp.status_code == 400
        assert resp.json()["code"] == 40001


class TestGetPortfolio:
    """GET /api/v1/portfolios/{id}(§3.6.5)。"""

    def test_get_existing(self, client_with_funds: TestClient) -> None:
        """查存在的组合。"""
        # 先创建
        create_resp = client_with_funds.post(
            "/api/v1/portfolios",
            json={
                "name": "测试",
                "weights": [{"code": "000001", "weight": 1.0}],
            },
        )
        pid = create_resp.json()["data"]["portfolio_id"]
        # 查
        resp = client_with_funds.get(f"/api/v1/portfolios/{pid}")
        assert resp.status_code == 200
        assert resp.json()["data"]["portfolio_id"] == pid

    def test_get_not_found(self, client_with_funds: TestClient) -> None:
        """不存在 -> 40002。"""
        resp = client_with_funds.get("/api/v1/portfolios/pf_nonexistent")
        assert resp.status_code == 404
        assert resp.json()["code"] == 40002


class TestListPortfolios:
    """GET /api/v1/portfolios。"""

    def test_list_empty(self, client_with_funds: TestClient) -> None:
        """空列表。"""
        resp = client_with_funds.get("/api/v1/portfolios")
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    def test_list_after_create(self, client_with_funds: TestClient) -> None:
        """创建后列表非空。"""
        client_with_funds.post("/api/v1/portfolios", json={"name": "A"})
        client_with_funds.post("/api/v1/portfolios", json={"name": "B"})
        resp = client_with_funds.get("/api/v1/portfolios")
        assert len(resp.json()["data"]) == 2


class TestDeletePortfolio:
    """DELETE /api/v1/portfolios/{id}。"""

    def test_delete_existing(self, client_with_funds: TestClient) -> None:
        """删除组合(级联删权重)。"""
        create_resp = client_with_funds.post(
            "/api/v1/portfolios",
            json={
                "name": "删除测试",
                "weights": [{"code": "000001", "weight": 1.0}],
            },
        )
        pid = create_resp.json()["data"]["portfolio_id"]
        resp = client_with_funds.delete(f"/api/v1/portfolios/{pid}")
        assert resp.status_code == 200
        assert resp.json()["data"]["deleted"] is True
        # 再查 -> 404
        resp2 = client_with_funds.get(f"/api/v1/portfolios/{pid}")
        assert resp2.status_code == 404

    def test_delete_not_found(self, client_with_funds: TestClient) -> None:
        """不存在 -> 40002。"""
        resp = client_with_funds.delete("/api/v1/portfolios/pf_nonexistent")
        assert resp.status_code == 404
        assert resp.json()["code"] == 40002


class TestImportFromPaper:
    """POST /api/v1/portfolios/import 从模拟持仓导入(§3.6.1)。"""

    def test_import_success(self, client_with_funds: TestClient) -> None:
        """从模拟持仓导入 -> 权重按市值占比。"""
        resp = client_with_funds.post(
            "/api/v1/portfolios/import",
            json={
                "name": "模拟导入",
            },
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["source"] == "import"
        assert len(data["weights"]) == 2  # 000001 + 000002
        # 权重和约 1.0
        total = sum(w["weight"] for w in data["weights"])
        assert total == pytest.approx(1.0, abs=0.01)

    def test_import_no_positions(self, client_with_funds: TestClient) -> None:
        """无模拟持仓 -> 40002。"""
        resp = client_with_funds.post(
            "/api/v1/portfolios/import",
            json={
                "account_id": "empty_account",
            },
        )
        assert resp.status_code == 404
        assert resp.json()["code"] == 40002


class TestDiagnosePortfolio:
    """GET /api/v1/portfolios/{id}/diagnosis(§3.6.6.1 / TP-03 / E8/E9/E12)。

    验证端点接线(含 select 导入)与七字段信封；fixture 基金均为 mixed(权益类)。
    """

    def test_diagnosis_returns_five_dims(self, client_with_funds: TestClient) -> None:
        """诊断返回五维 + 整体评级 + 信封。"""
        pid = client_with_funds.post(
            "/api/v1/portfolios",
            json={
                "name": "诊断测试",
                "weights": [{"code": "000001", "weight": 1.0}],
            },
        ).json()["data"]["portfolio_id"]

        resp = client_with_funds.get(f"/api/v1/portfolios/{pid}/diagnosis?risk_type=moderate")
        assert resp.status_code == 200
        body = resp.json()
        # 七字段信封(§2.21)
        assert body["code"] == 0
        assert body["data"] is not None
        assert "disclaimer" in body and body["disclaimer"]
        report = body["data"]
        assert report["portfolio_id"] == pid
        assert set(report["per_dim"]) == {"asset", "overseas", "industry", "style", "single"}
        assert report["rating"] in {"red", "yellow", "green"}
        # mixed 全权益 -> moderate(40-60%) 越界 -> 红(E8)
        assert report["per_dim"]["asset"]["status"] == "red"

    def test_diagnosis_not_found(self, client_with_funds: TestClient) -> None:
        """不存在 -> 40002。"""
        resp = client_with_funds.get("/api/v1/portfolios/pf_none/diagnosis")
        assert resp.status_code == 404
        assert resp.json()["code"] == 40002
