"""批算与分位表单测(P1-05，详设§3.3.9 / TP-01 §3.3-§4 / ADR-002 / E5)。

覆盖：分位表按 asset_class 分组百分位、货基排除、universe<5 退化全市场、
score_one 查表、batch_score_all、worker run_once(写 PG scores 表)。
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pandas as pd
import pytest

from domain.batch import (
    MIN_UNIVERSE,
    FundRawInput,
    batch_score_all,
    build_percentile_tables,
    score_one,
)


def _nav(factor: float = 1.0, days: int = 252) -> pd.Series:
    """生成净值序列(年化约 10%×factor)。"""
    return pd.Series([1.0 * (1.10 * factor) ** (i / 250) for i in range(days)])


def _equity_funds(n: int = 6) -> list[FundRawInput]:
    """n 只权益基金(足够 universe >=5)。"""
    return [
        FundRawInput(
            f"F{i}", "equity", _nav(1.0 + i * 0.05), aum=100.0 + i * 50, manager_excess_val=0.01 * i
        )
        for i in range(n)
    ]


class TestBuildPercentileTables:
    """§3.3.9 / E5 分位表构建。"""

    def test_factors_in_table(self) -> None:
        """分位表含五因子。"""
        pct = build_percentile_tables(_equity_funds())
        assert set(pct.tables.keys()) == {"ret", "risk", "perf", "scale", "manager"}

    def test_subscore_lookup(self) -> None:
        """查表得子分(O(1)，ADR-002)。"""
        pct = build_percentile_tables(_equity_funds())
        s = pct.sub_score("ret", "F0")
        assert s is not None
        assert 0 <= s <= 100

    def test_money_excluded_from_percentile(self) -> None:
        """E5：货基排除百分位(仅 scale 可有，其余不参与)。"""
        funds = _equity_funds() + [FundRawInput("M1", "money", _nav(1.01), aum=1000.0)]
        pct = build_percentile_tables(funds)
        # 货基不在 ret 分位表
        assert "M1" not in pct.tables.get("ret", {})

    def test_universe_below_min_fallback_all(self) -> None:
        """universe < MIN_UNIVERSE -> 退化全市场百分位。"""
        assert MIN_UNIVERSE == 5
        # 仅 3 只 equity(同组 <5) -> 退化
        funds = [
            FundRawInput(f"F{i}", "equity", _nav(1.0 + i * 0.1), aum=100.0, manager_excess_val=0.01)
            for i in range(3)
        ]
        pct = build_percentile_tables(funds)
        # 仍能算出子分(退化全市场)
        assert pct.sub_score("ret", "F0") is not None

    def test_scale_uses_scale_health(self) -> None:
        """scale 用 scale_health(非线性 E4)，非百分位。"""
        funds = [FundRawInput("F0", "equity", _nav(), aum=100.0)]  # aum∈[2,500] -> 100
        pct = build_percentile_tables(funds)
        assert pct.tables["scale"]["F0"] == 100.0


class TestScoreOne:
    """§3.3.9 score_one(查分位表)。"""

    def test_composite_in_range(self) -> None:
        funds = _equity_funds()
        pct = build_percentile_tables(funds)
        res = score_one("F0", "equity", pct, nav=funds[0].nav, aum=100.0, manager_excess_val=0.01)
        assert res["composite"] is not None
        assert 0 <= res["composite"] <= 100

    def test_money_returns_none_composite(self) -> None:
        """E5：货基 composite=None。"""
        pct = build_percentile_tables(_equity_funds())
        res = score_one("M1", "money", pct)
        assert res["composite"] is None
        assert res["excluded"] == "money"

    def test_returns_factors_and_scope(self) -> None:
        funds = _equity_funds()
        pct = build_percentile_tables(funds)
        res = score_one("F0", "equity", pct, nav=funds[0].nav, aum=100.0)
        assert set(res["factors"].keys()) == {"ret", "risk", "perf", "scale", "manager"}
        assert res["scope"] == "equity"


class TestBatchScoreAll:
    """§3.3.9 batch_score_all。"""

    def test_scores_all_funds(self) -> None:
        funds = _equity_funds(6)
        pct = build_percentile_tables(funds)
        results = batch_score_all(funds, pct)
        assert len(results) == 6
        assert all(r["composite"] is not None for r in results.values())

    def test_money_excluded_in_batch(self) -> None:
        funds = _equity_funds(5) + [FundRawInput("M1", "money", _nav(1.01), aum=1000.0)]
        pct = build_percentile_tables(funds)
        results = batch_score_all(funds, pct)
        assert results["M1"]["composite"] is None


@pytest.mark.db
class TestBatchWorker:
    """§3.3.9 worker run_once(写 PG scores 表)。"""

    def test_run_once_writes_scores(self, engine, monkeypatch: pytest.MonkeyPatch) -> None:
        """run_once -> upsert scores 表(§3.3.9)。"""
        from sqlalchemy import text
        from sqlalchemy.orm import Session, sessionmaker

        import workers.batch as wbatch
        from infra.db.models import Fund, Nav

        # 注入测试 DB
        TestSession = sessionmaker(bind=engine)
        monkeypatch.setattr(wbatch, "SessionLocal", TestSession)

        with Session(engine) as s:
            for i in range(6):
                s.add(
                    Fund(
                        code=f"F{i}",
                        name=f"基金{i}",
                        type_="mixed",
                        source="AkShare",
                        as_of=date.today(),
                    )
                )
                base = date(2024, 1, 1)
                for d in range(30):
                    s.add(
                        Nav(
                            code=f"F{i}",
                            trade_date=base + timedelta(days=d),
                            nav=Decimal("1.0")
                            * (Decimal("1.1") ** (Decimal(str(d)) / Decimal("250"))),
                            acc_nav=Decimal("2.0"),
                            adj_nav=Decimal("1.0")
                            * (Decimal("1.1") ** (Decimal(str(d)) / Decimal("250"))),
                            is_estimate=False,
                            source="AkShare",
                            as_of=date.today(),
                        )
                    )
            s.commit()

        stats = wbatch.run_once()
        assert stats["funds"] == 6
        assert stats["scored"] >= 1  # 有 NAV 的基金被评分

        with Session(engine) as s:
            cnt = s.execute(text("SELECT count(*) FROM scores")).scalar()
        assert cnt >= 1  # scores 表已写
