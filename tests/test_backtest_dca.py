"""定投回测单测(P1-07d，§3.5.8 / TP-04 / E3 红线)。

纯逻辑：run_dca 定投回测(后复权净值/申购费/赎回费/IRR/回撤)。
"""

from __future__ import annotations

import pandas as pd
import pytest

from domain.backtest_dca import BUY_FEE_RATE, FREQ_RULES, run_dca


def _steady_nav(days: int = 252, annual: float = 0.08) -> pd.Series:
    """稳定上涨 NAV(年化 annual)。"""
    return pd.Series(
        [1.0 * (1 + annual) ** (i / 250) for i in range(days)],
        index=pd.date_range("2024-01-01", periods=days),
    )


class TestRunDca:
    """TP-04 §3.1 _run_dca。"""

    def test_basic_result(self) -> None:
        """基本回测：返回完整字段。"""
        r = run_dca(_steady_nav(), freq="monthly", amount=1000)
        assert r.cum_invest > 0
        assert r.gross_value > 0
        assert r.final_value > 0
        assert r.shares > 0
        assert r.invest_count > 0

    def test_steady_up_profit(self) -> None:
        """稳定上涨 -> 利润为正。"""
        r = run_dca(_steady_nav(annual=0.10), freq="monthly", amount=1000)
        assert r.profit > 0
        assert r.irr is not None
        assert r.irr > 0  # 正收益

    def test_declining_loss(self) -> None:
        """下跌 -> 利润为负。"""
        nav = pd.Series(
            [1.0 * (0.92 ** (i / 250)) for i in range(252)],
            index=pd.date_range("2024-01-01", periods=252),
        )
        r = run_dca(nav, freq="monthly", amount=1000)
        assert r.profit < 0

    def test_buy_fee_deducted(self) -> None:
        """申购费：份额 = amount / (nav * (1+fee))。"""
        r_no_fee = run_dca(_steady_nav(), freq="monthly", amount=1000, buy_fee=0.0)
        r_fee = run_dca(_steady_nav(), freq="monthly", amount=1000, buy_fee=0.015)
        # 有申购费 -> 份额更少
        assert r_fee.shares < r_no_fee.shares

    def test_redeem_fee_deducted(self) -> None:
        """赎回费：final_value < gross_value。"""
        r = run_dca(_steady_nav(), freq="monthly", amount=1000, redeem_fee_rate=0.005)
        assert r.redeem_fee > 0
        assert r.final_value < r.gross_value

    def test_e3_final_val_after_fee(self) -> None:
        """E3：final_value = gross_value - redeem_fee。"""
        r = run_dca(_steady_nav(), freq="monthly", amount=1000, redeem_fee_rate=0.01)
        assert r.final_value == pytest.approx(r.gross_value - r.redeem_fee)

    def test_insufficient_nav(self) -> None:
        """NAV 不足(<2) -> 空 DcaResult。"""
        r = run_dca(pd.Series([1.0]), freq="monthly")
        assert r.cum_invest == 0
        assert r.shares == 0

    def test_freq_rules(self) -> None:
        """频率常量(TP-04)。"""
        assert FREQ_RULES["monthly"] == "ME"
        assert FREQ_RULES["weekly"] == "W-MON"
        assert FREQ_RULES["quarterly"] == "QE"
        assert BUY_FEE_RATE == 0.0015

    def test_weekly_more_investments(self) -> None:
        """周投比月投次数多。"""
        r_monthly = run_dca(_steady_nav(), freq="monthly", amount=1000)
        r_weekly = run_dca(_steady_nav(), freq="weekly", amount=1000)
        assert r_weekly.invest_count > r_monthly.invest_count

    def test_nav_curve_returned(self) -> None:
        """净值曲线返回(前端绘图用)。"""
        r = run_dca(_steady_nav(), freq="monthly", amount=1000)
        assert len(r.nav_curve) > 0
        assert "date" in r.nav_curve[0]
        assert "nav" in r.nav_curve[0]
        assert "shares" in r.nav_curve[0]
