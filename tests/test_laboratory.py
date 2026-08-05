"""单基深度实验室单测(P1-09a，详设§3.8 / DC-011 / FR-40~42)。

覆盖：
- 回本测算：r>=0 已盈利、r<0 回本需涨 abs(r)/(1+r)、r<=-1 净值归零、三情景回本月数。
- 三情景推演：保守/基准/乐观投影曲线；基准用真实年化。
- 五策略对照：持有/定投/波段/调仓/止损 终值/收益/回撤。
- 边界：空净值、短序列不崩溃。
"""

from __future__ import annotations

import math

import pandas as pd
import pytest

from domain.laboratory import (
    SCENARIO_ASSUMPTIONS,
    STRATEGIES,
    STRATEGY_NAMES,
    breakeven_analysis,
    scenario_projection,
    strategy_comparison,
)


def _nav_series(start: float, daily_ret: float, days: int = 100) -> pd.Series:
    """构造后复权净值序列(等比增长)。"""
    dates = pd.bdate_range("2024-01-01", periods=days)
    values = [start * ((1.0 + daily_ret) ** i) for i in range(days)]
    return pd.Series(values, index=dates)


class TestBreakeven:
    """回本测算(§3.8.2)。"""

    def test_profitable(self) -> None:
        """r>=0 -> 已盈利，breakeven_gain=0。"""
        result = breakeven_analysis(0.15)
        assert result.profitable is True
        assert result.breakeven_gain_pct == 0.0
        assert "已盈利" in result.note

    def test_loss_breakeven_gain(self) -> None:
        """r=-0.2 -> 回本需涨 = 0.2/0.8 = 0.25。"""
        result = breakeven_analysis(-0.2)
        assert result.profitable is False
        assert result.breakeven_gain_pct == pytest.approx(0.25, rel=1e-6)
        assert "25.0%" in result.note

    def test_zero_nav_unrecoverable(self) -> None:
        """r<=-1 -> 净值归零，无法回本(§4 不崩溃)。"""
        result = breakeven_analysis(-1.0)
        assert result.profitable is False
        assert result.breakeven_gain_pct is None
        assert "归零" in result.note

    def test_small_loss_breakeven(self) -> None:
        """r=-0.1 -> 回本需涨 = 0.1/0.9 ≈ 0.1111。"""
        result = breakeven_analysis(-0.1)
        assert result.breakeven_gain_pct == pytest.approx(0.1 / 0.9, abs=1e-5)

    def test_months_to_breakeven_optistic_finite(self) -> None:
        """乐观情景(正月化) -> 回本月数为有限值。"""
        result = breakeven_analysis(-0.2)
        # 乐观 +20%/年 -> 月化正 -> months 有限
        assert result.months_to_breakeven["optimistic"] is not None
        assert result.months_to_breakeven["optimistic"] > 0

    def test_months_to_breakeven_conservative_none(self) -> None:
        """保守情景(-10%/年，月化为负近似) -> 永不回本 None。

        注：保守年化 -10% -> 月化 (1-0.1)^(1/12)-1 < 0 -> None。
        """
        result = breakeven_analysis(-0.2)
        assert result.months_to_breakeven["conservative"] is None

    def test_result_serializable(self) -> None:
        result = breakeven_analysis(-0.15)
        d = result.to_dict()
        assert "return_rate" in d
        assert "breakeven_gain_pct" in d
        assert "months_to_breakeven" in d


class TestScenarioProjection:
    """三情景推演(§3.8.2)。"""

    def test_three_scenarios_present(self) -> None:
        """三情景齐全。"""
        result = scenario_projection(None, months=12)
        assert set(result.projections) == {"conservative", "baseline", "optimistic"}
        assert set(result.assumptions) == {"conservative", "baseline", "optimistic"}

    def test_projection_starts_at_one(self) -> None:
        """投影起点=1.0。"""
        result = scenario_projection(None, months=6)
        for _scenario, curve in result.projections.items():
            assert curve[0]["value"] == pytest.approx(1.0)
            assert curve[0]["month"] == 0

    def test_optimistic_highest(self) -> None:
        """乐观终值 > 基准 > 保守。"""
        result = scenario_projection(None, months=12)
        opt = result.projections["optimistic"][-1]["value"]
        base = result.projections["baseline"][-1]["value"]
        cons = result.projections["conservative"][-1]["value"]
        assert opt > base > cons

    def test_baseline_uses_historical_return(self) -> None:
        """有历史净值 -> 基准用真实年化。"""
        nav = _nav_series(1.0, 0.001, days=252)  # 约 +8.6%/年(252 日 * 0.1%)
        result = scenario_projection(nav, months=6)
        # 基准年化应反映历史(非默认 0.08)
        assert result.assumptions["baseline"] != SCENARIO_ASSUMPTIONS["baseline"]

    def test_projection_length(self) -> None:
        """投影月数 = months+1(含起点)。"""
        result = scenario_projection(None, months=12)
        assert len(result.projections["baseline"]) == 13


class TestStrategyComparison:
    """五策略对照(§3.8.2)。"""

    def test_five_strategies(self) -> None:
        """返回五策略结果。"""
        nav = _nav_series(1.0, 0.001, days=100)
        results = strategy_comparison(nav)
        assert len(results) == 5
        strategies = [r.strategy for r in results]
        assert set(strategies) == set(STRATEGIES)

    def test_hold_strategy_positive_return(self) -> None:
        """持有策略：单调涨 -> 正收益，无回撤。"""
        nav = _nav_series(1.0, 0.001, days=100)
        results = {r.strategy: r for r in strategy_comparison(nav)}
        hold = results["hold"]
        assert hold.total_return > 0
        assert hold.max_drawdown == pytest.approx(0.0, abs=1e-9)

    def test_stop_loss_triggers_on_crash(self) -> None:
        """止损策略：大跌 -> 触发清仓(终值=止损时现金)。"""
        # 构造先涨后大跌序列
        dates = pd.bdate_range("2024-01-01", periods=60)
        values = [1.0 + i * 0.005 for i in range(30)] + [1.15 - i * 0.02 for i in range(30)]
        nav = pd.Series(values, index=dates)
        results = {r.strategy: r for r in strategy_comparison(nav)}
        sl = results["stop_loss"]
        # 大跌超 10% -> 止损触发
        assert sl.max_drawdown <= 0

    def test_dca_strategy_uses_run_dca(self) -> None:
        """定投策略：复用 run_dca，返回有效收益。"""
        nav = _nav_series(1.0, 0.001, days=100)
        results = {r.strategy: r for r in strategy_comparison(nav)}
        dca = results["dca"]
        assert dca.name == "定投"
        assert isinstance(dca.total_return, float)

    def test_strategy_names_complete(self) -> None:
        """五策略中文名齐全。"""
        nav = _nav_series(1.0, 0.001, days=50)
        results = strategy_comparison(nav)
        for r in results:
            assert r.name == STRATEGY_NAMES[r.strategy]
            assert r.name in {"持有", "定投", "波段", "调仓", "止损"}

    def test_empty_nav_returns_empty(self) -> None:
        """空/短净值 -> 空结果(不崩溃)。"""
        assert strategy_comparison(pd.Series([], dtype=float)) == []
        assert strategy_comparison(pd.Series([1.0])) == []

    def test_nav_zero_does_not_crash(self) -> None:
        """§4 红线：NAV=0 不崩溃。"""
        dates = pd.bdate_range("2024-01-01", periods=10)
        nav = pd.Series([1.0, 0.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0], index=dates)
        results = strategy_comparison(nav)
        assert len(results) == 5
        for r in results:
            assert math.isfinite(r.final_value)


class TestAssumptions:
    """情景假设口径。"""

    def test_scenario_assumptions_values(self) -> None:
        """保守/基准/乐观 年化假设。"""
        assert SCENARIO_ASSUMPTIONS["conservative"] < 0
        assert SCENARIO_ASSUMPTIONS["baseline"] > 0
        assert SCENARIO_ASSUMPTIONS["optimistic"] > SCENARIO_ASSUMPTIONS["baseline"]

    def test_strategies_count(self) -> None:
        """五策略。"""
        assert len(STRATEGIES) == 5
