"""组合回测单测(P1-08c，详设§3.6.7 / TP-04 §4 / E3/E14 红线)。

覆盖：
- E3：后复权净值口径(不单独设分红再投)。
- E14：基准按 asset_class 自动选(权益->沪深300全收益 / 债券->中债综合财富 / QDII->标普500)。
- 组合日收益 = Σ w_i × ret_i(严格时序，无未来函数)。
- 累计收益/最大回撤(负值 E5)/夏普/超额。
- 边界：成分缺失 partial、样本不足 low_sample、空组合、权重归一、基准缺失。
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from domain.backtest_portfolio import (
    TOTAL_RETURN_BENCH,
    pick_benchmark,
    portfolio_backtest,
)


def _nav_series(start: float, daily_ret: float, days: int = 100) -> pd.Series:
    """构造后复权净值序列(等比增长)。"""
    dates = pd.bdate_range("2024-01-01", periods=days)
    values = [start * ((1.0 + daily_ret) ** i) for i in range(days)]
    return pd.Series(values, index=dates)


class TestPickBenchmark:
    """E14：基准按 asset_class 加权主导项选。"""

    def test_equity_dominant(self) -> None:
        weights = {"A": 0.6, "B": 0.4}
        ft = {"A": "stock", "B": "bond"}
        assert pick_benchmark(weights, ft) == TOTAL_RETURN_BENCH["equity"]

    def test_bond_dominant(self) -> None:
        weights = {"A": 0.3, "B": 0.7}
        ft = {"A": "stock", "B": "bond"}
        assert pick_benchmark(weights, ft) == TOTAL_RETURN_BENCH["bond"]

    def test_qdii_dominant(self) -> None:
        weights = {"A": 0.2, "B": 0.8}
        ft = {"A": "stock", "B": "qdii"}
        assert pick_benchmark(weights, ft) == TOTAL_RETURN_BENCH["qdii"]

    def test_no_fund_types_defaults_mixed(self) -> None:
        """无 fund_types -> 按 mixed 推断 -> 沪深300全收益。"""
        weights = {"A": 1.0}
        assert pick_benchmark(weights) == TOTAL_RETURN_BENCH["mixed"]

    def test_benchmark_table_covers_all_asset_classes(self) -> None:
        """E14 全收益指数表完整。"""
        for ac in ["equity", "mixed", "bond", "money", "qdii", "alt"]:
            assert ac in TOTAL_RETURN_BENCH


class TestPortfolioBacktest:
    """组合回测核心算法(TP-04 §4)。"""

    def test_single_fund_cum_return(self) -> None:
        """单基组合：累计收益 = 个基累计收益。"""
        nav = _nav_series(1.0, 0.001, days=100)  # 日涨 0.1%
        result = portfolio_backtest({"A": nav}, {"A": 1.0})
        # 预期累计 ≈ (1.001^99 - 1)
        expected = (1.001**99) - 1.0
        assert result.cum_return == pytest.approx(expected, rel=1e-6)
        assert result.sharpe is not None and result.sharpe > 0

    def test_weighted_two_funds(self) -> None:
        """两基加权：组合日收益 = 0.5*ret_A + 0.5*ret_B。"""
        nav_a = _nav_series(1.0, 0.002, days=100)
        nav_b = _nav_series(1.0, 0.001, days=100)
        result = portfolio_backtest({"A": nav_a, "B": nav_b}, {"A": 0.5, "B": 0.5})
        assert result.cum_return > 0
        assert result.max_drawdown == pytest.approx(0.0, abs=1e-9)  # 单调涨 -> 无回撤

    def test_weight_normalization(self) -> None:
        """权重和≠1 -> 内部归一(和=1.2 仍计算)。"""
        nav = _nav_series(1.0, 0.001, days=50)
        result = portfolio_backtest({"A": nav}, {"A": 1.2})
        # 归一后等价于单基满仓
        expected = (1.001**49) - 1.0
        assert result.cum_return == pytest.approx(expected, rel=1e-6)

    def test_max_drawdown_negative(self) -> None:
        """E5：最大回撤为负值。"""
        # 构造先涨后跌的序列
        dates = pd.bdate_range("2024-01-01", periods=100)
        values = [1.0] * 50 + [1.0 - i * 0.01 for i in range(50)]  # 50天后持续下跌
        nav = pd.Series(values[:100], index=dates)
        result = portfolio_backtest({"A": nav}, {"A": 1.0})
        assert result.max_drawdown < 0

    def test_benchmark_comparison_e14(self) -> None:
        """E14：有基准 -> 计算超额。"""
        port_nav = _nav_series(1.0, 0.002, days=100)
        bench_nav = _nav_series(1.0, 0.001, days=100)  # 基准涨得慢
        result = portfolio_backtest(
            {"A": port_nav}, {"A": 1.0}, bench_nav=bench_nav, bench_code="H00300.SH"
        )
        assert result.bench == "H00300.SH"
        assert result.bench_cum_return is not None and result.bench_cum_return > 0
        assert result.excess_cum is not None and result.excess_cum > 0  # 组合超额
        assert result.excess_ann is not None

    def test_no_benchmark_returns_none_metrics(self) -> None:
        """无基准 -> bench 指标 None(仅组合指标)。"""
        nav = _nav_series(1.0, 0.001, days=100)
        result = portfolio_backtest({"A": nav}, {"A": 1.0}, bench_nav=None)
        assert result.bench_cum_return is None
        assert result.excess_cum is None
        assert result.cum_return > 0  # 组合指标仍返回

    def test_partial_when_fund_missing(self) -> None:
        """成分缺失(有权重无净值)-> partial=True。"""
        nav = _nav_series(1.0, 0.001, days=100)
        result = portfolio_backtest(
            {"A": nav, "B": None}, {"A": 0.5, "B": 0.5}  # type: ignore[dict-item]
        )
        assert result.partial is True
        assert result.cum_return > 0  # 仍用 A 计算

    def test_low_sample_flag(self) -> None:
        """样本<60 日 -> low_sample=True。"""
        nav = _nav_series(1.0, 0.001, days=30)
        result = portfolio_backtest({"A": nav}, {"A": 1.0})
        assert result.low_sample is True

    def test_empty_nav_dict_returns_empty(self) -> None:
        """空净值 -> 空结果(不崩溃)。"""
        result = portfolio_backtest({}, {"A": 1.0})
        assert result.cum_return == 0.0

    def test_nav_zero_does_not_crash(self) -> None:
        """§4 红线：NAV=0 不崩溃(pct_change 产生 inf/nan 被 fillna 处理)。"""
        dates = pd.bdate_range("2024-01-01", periods=10)
        nav = pd.Series([1.0, 0.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0], index=dates)
        result = portfolio_backtest({"A": nav}, {"A": 1.0})
        # 不崩溃即通过；cum_return 为有限数
        assert np.isfinite(result.cum_return)

    def test_nav_curve_sampled(self) -> None:
        """净值曲线输出(采样至多 200 点)。"""
        nav = _nav_series(1.0, 0.001, days=100)
        result = portfolio_backtest({"A": nav}, {"A": 1.0})
        assert len(result.nav_curve) > 0
        assert "date" in result.nav_curve[0]
        assert "nav" in result.nav_curve[0]

    def test_result_serializable(self) -> None:
        """结果可序列化为 dict。"""
        nav = _nav_series(1.0, 0.001, days=100)
        result = portfolio_backtest({"A": nav}, {"A": 1.0})
        d = result.to_dict()
        assert "cum_return" in d
        assert "max_drawdown" in d
        assert "sharpe" in d
        assert "nav_curve" in d


class TestNoFutureFunction:
    """防未来函数(TP-04 §4)：日收益用 t-1->t，不窥探未来。"""

    def test_returns_use_prior_day_only(self) -> None:
        """组合收益 = Σ w_i × (nav_t - nav_{t-1})/nav_{t-1}。

        验证：等比增长序列 -> 每日收益恒定 0.01，累计 = (1.01^49)-1。
        """
        dates = pd.bdate_range("2024-01-01", periods=50)
        values = [1.0 * (1.01**i) for i in range(50)]  # 等比增长
        nav = pd.Series(values, index=dates)
        result = portfolio_backtest({"A": nav}, {"A": 1.0})
        # 等比增长 -> 每日收益恒定 0.01
        assert result.cum_return == pytest.approx((1.01**49) - 1.0, rel=1e-6)
