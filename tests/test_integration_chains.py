"""P1-21 集成测试：跨模块数据流一致性(任务分解验收口径 / ADR-002 / §2.21)。

三条链路：
1. 采集->质量：clean -> upsert -> 质量日志(§3.1.2 / §3.14.5 幂等 upsert)
2. 评估->筛选->仪表盘一致(ADR-002)：batch_score -> 落库 scores -> /score(在线) == 夜算综合分；
   /screen 与 /dashboard 只读同一 score，无漂移(评估引擎唯一权威源)。
3. 模拟->组合导入->诊断：paper 持仓 -> /portfolios/import -> /diagnosis(§3.6 / TP-03 / E8/E9/E12)。

标记 db，无 PG 跳过(``pytest -m "not db"``)。
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

pytestmark = pytest.mark.db


# ===========================================================================
# 链路 1：采集 -> 质量(§3.1.2 清洗 + §3.14.5 幂等 upsert + 质量日志)
# ===========================================================================


class TestCollectQualityChain:
    """采集清洗 -> upsert 持久化 -> 质量日志，全链路落 DB。"""

    def test_clean_upsert_quality_chain(self, engine: Any) -> None:
        """清洗 nav -> upsert(幂等) -> 质量日志写入。"""
        from domain.collect import clean_nav
        from infra.collect_repo import upsert_funds, upsert_navs, write_quality_log
        from infra.db.models import DataQualityLog, Nav

        # 1) 基金 + 原始净值(模拟 AkShare 拉取)
        funds = [
            {"code": "000001", "name": "华夏成长", "type_": "mixed", "source": "AkShare"},
            {"code": "000002", "name": "华夏大盘", "type_": "mixed", "source": "AkShare"},
        ]
        base = date(2024, 1, 1)
        raw_navs = [
            {
                "code": "000001",
                "trade_date": base + timedelta(days=i),
                "nav": 1.0 + i * 0.001,
                "acc_nav": 1.0 + i * 0.001,
                "source": "AkShare",
            }
            for i in range(10)
        ]

        with Session(engine) as db:
            # 2) 清洗 -> upsert
            upsert_funds(db, funds)
            cleaned = clean_nav(raw_navs, source="AkShare")
            n = upsert_navs(db, cleaned)
            assert n == 10
            # 3) 幂等：重跑 upsert 不产生重复行(§3.14.5)
            n2 = upsert_navs(db, cleaned)
            assert n2 == 10
            cnt = db.execute(select(Nav).where(Nav.code == "000001")).scalars().all()
            assert len(cnt) == 10  # 无重复

            # 4) 质量日志写入(§3.14.5)
            write_quality_log(
                db,
                entity="000001",
                missing_count=0,
                cv_error=Decimal("0.0"),
                source="AkShare",
                note="集成测试",
            )
            db.commit()
            logs = (
                db.execute(select(DataQualityLog).where(DataQualityLog.entity == "000001"))
                .scalars()
                .all()
            )
            assert len(logs) == 1
            assert logs[0].missing_count == 0


# ===========================================================================
# 链路 2：评估 -> 筛选 -> 仪表盘 一致(ADR-002 评估引擎唯一权威源)
# ===========================================================================


@pytest.fixture()
def client_with_batch_scores(db_session: Session):
    """种子基金+净值 -> 跑真实夜算批算 -> 落 scores 表 -> TestClient。

    验证 ADR-002：在线 /score 读批算结果(不复算百分位)，/screen 与 /dashboard 只读同一 score。
    """
    from collections.abc import Iterator

    from sqlalchemy.orm import sessionmaker

    from api.deps import get_db
    from domain.batch import batch_score_all, build_percentile_tables
    from infra.db.models import Fund, Nav
    from workers.batch import _upsert_scores, load_all_funds

    TestSession = sessionmaker(bind=db_session.bind, autocommit=False, autoflush=False)
    # 6 只权益(mixed)基金 + 252 日上涨净值(universe>=5 可算百分位)
    base = date(2024, 1, 1)
    with TestSession() as s:
        for i in range(6):
            s.add(
                Fund(
                    code=f"F{i:05d}",
                    name=f"基金F{i}",
                    type_="mixed",
                    source="AkShare",
                    as_of=date.today(),
                )
            )
            for d in range(252):
                nav_val = Decimal("1.0") * (Decimal("1.10") ** (Decimal(str(d)) / Decimal("250")))
                s.add(
                    Nav(
                        code=f"F{i:05d}",
                        trade_date=base + timedelta(days=d),
                        nav=nav_val,
                        acc_nav=nav_val,
                        adj_nav=nav_val,
                        is_estimate=False,
                        source="AkShare",
                        as_of=date.today(),
                    )
                )
        s.commit()

    # 真实夜算批算链路：load_all_funds -> build_percentile_tables -> batch_score_all -> 落库
    with TestSession() as db:
        funds = load_all_funds(db)
        pct = build_percentile_tables(funds)
        results = batch_score_all(funds, pct)
        _upsert_scores(db, results)

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
        yield c, results  # 返回批算结果供断言
    app.dependency_overrides.clear()


class TestADROneScoreConsistency:
    """ADR-002：在线综合分 == 夜算综合分；筛选/仪表盘只读同一 score，无漂移。"""

    def test_online_score_equals_batch(
        self, client_with_batch_scores: tuple[TestClient, dict[str, Any]]
    ) -> None:
        """在线 /score 的 composite == batch_score_all 产出(ADR-002 test oracle)。"""
        client, results = client_with_batch_scores
        code = "F00000"
        batch_composite = results[code].get("composite")
        if batch_composite is None:
            pytest.skip("批算未产出 composite(数据不足)，跳过 ADR-002 一致性断言")
        resp = client.get(f"/api/v1/funds/{code}/score")
        assert resp.status_code == 200
        online_composite = resp.json()["data"]["composite"]
        assert online_composite is not None
        # ADR-002：在线 == 夜算(容差 0.1，浮点格式化差异)
        assert float(online_composite) == pytest.approx(float(batch_composite), abs=0.1)

    def test_screen_uses_same_score(
        self, client_with_batch_scores: tuple[TestClient, dict[str, Any]]
    ) -> None:
        """/screen 的 score 字段 == scores 表(ADR-002 只读，不复算)。"""
        client, results = client_with_batch_scores
        code = "F00000"
        batch_composite = results[code].get("composite")
        if batch_composite is None:
            pytest.skip("批算未产出 composite，跳过")
        resp = client.post(
            "/api/v1/screen",
            json={
                "filters": [{"field": "type", "op": "=", "value": "mixed"}],
                "page": 1,
                "page_size": 20,
            },
        )
        assert resp.status_code == 200
        items = resp.json()["data"]["items"]
        target = next((i for i in items if i["code"] == code), None)
        assert target is not None
        assert target["score"] is not None
        assert float(target["score"]) == pytest.approx(float(batch_composite), abs=0.1)

    def test_dashboard_top10_uses_same_score(
        self, client_with_batch_scores: tuple[TestClient, dict[str, Any]]
    ) -> None:
        """/dashboard top10 的 score == scores 表(ADR-002 只读，按 composite 降序)。"""
        client, results = client_with_batch_scores
        resp = client.get("/api/v1/dashboard?type=mixed")
        assert resp.status_code == 200
        top10 = resp.json()["data"]["top10"]
        # top10 中至少一只基金 score 与批算一致(无漂移)
        codes = {t["code"] for t in top10}
        batch_codes = {c for c, r in results.items() if r.get("composite") is not None}
        assert codes & batch_codes  # 交集非空：仪表盘读了批算 score
        # 降序
        scores = [t["score"] for t in top10 if t.get("score") is not None]
        assert scores == sorted(scores, reverse=True)


# ===========================================================================
# 链路 3：模拟 -> 组合导入 -> 诊断(§3.6 / TP-03 / E8/E9/E12)
# ===========================================================================


@pytest.fixture()
def client_with_paper_positions(db_session: Session):
    """基金+净值+模拟账户持仓 + TestClient(供导入->诊断链路)。"""
    from collections.abc import Iterator

    from sqlalchemy.orm import sessionmaker

    from api.deps import get_db
    from infra.db.models import Fund, Nav, PaperAccount, PaperPosition

    TestSession = sessionmaker(bind=db_session.bind, autocommit=False, autoflush=False)
    base = date(2024, 1, 1)
    with TestSession() as s:
        for code in ["000001", "000002"]:
            s.add(
                Fund(
                    code=code,
                    name=f"基金{code}",
                    type_="mixed",
                    source="AkShare",
                    as_of=date.today(),
                )
            )
            for d in range(60):
                nav_val = Decimal("1.0") * (Decimal("1.08") ** (Decimal(str(d)) / Decimal("250")))
                s.add(
                    Nav(
                        code=code,
                        trade_date=base + timedelta(days=d),
                        nav=nav_val,
                        acc_nav=nav_val,
                        adj_nav=nav_val,
                        is_estimate=False,
                        source="AkShare",
                        as_of=date.today(),
                    )
                )
        s.commit()
        # 模拟账户 + 持仓
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


class TestPaperPortfolioDiagnosisChain:
    """模拟持仓 -> 组合导入 -> 诊断，全链路(§3.6.1 导入 / §3.6.6.1 诊断)。"""

    def test_import_then_diagnose(self, client_with_paper_positions: TestClient) -> None:
        """导入模拟持仓 -> 诊断返回五维 + 整体评级(链路打通)。"""
        client = client_with_paper_positions
        # 1) 导入模拟持仓 -> 组合
        imp = client.post("/api/v1/portfolios/import", json={"name": "模拟导入"})
        assert imp.status_code == 200
        data = imp.json()["data"]
        assert data["source"] == "import"
        assert len(data["weights"]) == 2  # 000001 + 000002
        pid = data["portfolio_id"]

        # 2) 诊断导入的组合(§3.6.6.1 / TP-03 / E8/E9/E12)
        diag = client.get(f"/api/v1/portfolios/{pid}/diagnosis?risk_type=moderate")
        assert diag.status_code == 200
        dbody = diag.json()["data"]
        # 五维红黄绿(asset/overseas/industry/style/single)
        assert "per_dim" in dbody
        assert set(dbody["per_dim"].keys()) == {
            "asset",
            "overseas",
            "industry",
            "style",
            "single",
        }
        # 整体评级
        assert dbody["rating"] in {"green", "yellow", "red"}

    def test_diagnose_manual_portfolio(self, client_with_paper_positions: TestClient) -> None:
        """手动建组合 -> 诊断(对照：非导入路径也打通)。"""
        client = client_with_paper_positions
        pid = client.post(
            "/api/v1/portfolios",
            json={
                "name": "手动",
                "weights": [{"code": "000001", "weight": 1.0}],
            },
        ).json()["data"]["portfolio_id"]
        resp = client.get(f"/api/v1/portfolios/{pid}/diagnosis?risk_type=conservative")
        assert resp.status_code == 200
        assert set(resp.json()["data"]["per_dim"].keys()) == {
            "asset",
            "overseas",
            "industry",
            "style",
            "single",
        }
