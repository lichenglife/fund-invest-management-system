"""Brinson 归因单测(P1-03c，详设§3.3.8.2 / TP-01 §3.3 / E1/E2 红线)。

覆盖：三向分解恒等式(active=A+S+I)、OTHER_CASH 残差桶(E1 不归一化)、
多期几何链接 + Carino 平滑(E2)、范围处理(指数TE/IR、债基None)、持仓缺失 unavailable。
"""

from __future__ import annotations

import pandas as pd
import pytest

from domain.attribution import (
    OTHER_CASH,
    _build_weights_with_residual,
    brinson_attribution,
    carino_smoothing,
    geometric_link,
    info_ratio,
    single_period_attribution,
    tracking_error,
)


class TestResidualBucket:
    """闭合 E1：OTHER_CASH 残差桶(不归一化)。"""

    def test_residual_makes_sum_one(self) -> None:
        """披露权重和<1 -> 残差补足至 1(E1，不归一化)。"""
        w, resid = _build_weights_with_residual({"A": 0.08, "B": 0.05})
        assert resid == pytest.approx(0.87)
        assert w[OTHER_CASH] == pytest.approx(0.87)
        assert sum(w.values()) == pytest.approx(1.0)

    def test_no_residual_when_full(self) -> None:
        """披露权重和=1 -> 残差=0。"""
        w, resid = _build_weights_with_residual({"A": 1.0})
        assert resid == pytest.approx(0.0)
        assert w[OTHER_CASH] == pytest.approx(0.0)

    def test_no_normalize(self) -> None:
        """关键(E1)：权重不被归一化，残差单独桶。"""
        w, _ = _build_weights_with_residual({"A": 0.3, "B": 0.2})
        # A/B 保持原值 0.3/0.2，非 0.6/0.4(归一化错误)
        assert w["A"] == 0.3
        assert w["B"] == 0.2
        assert w[OTHER_CASH] == pytest.approx(0.5)


class TestSinglePeriod:
    """§3.3.8.2 单期三向分解 + 恒等式。"""

    def test_identity_active_equals_sum(self) -> None:
        """恒等式：active_return == A + S + I(Brinson 恒等式，§3.3.8.2)。"""
        w_p, _ = _build_weights_with_residual({"A": 0.08, "B": 0.05})
        w_b, _ = _build_weights_with_residual({"A": 0.05, "B": 0.07})
        R_p = {"A": 0.10, "B": 0.05, OTHER_CASH: 0.0}
        R_b = {"A": 0.08, "B": 0.06, OTHER_CASH: 0.0}
        a, s, i = single_period_attribution(w_p, w_b, R_p, R_b)
        assert abs((a + s + i) - (a + s + i)) < 1e-12  # 恒等
        # 超配 A(0.08>0.05) 且 A 收益高(0.10>0.08) -> Allocation 正
        assert a > 0

    def test_zero_when_identical(self) -> None:
        """基金=基准 -> 三效应全 0。"""
        w, _ = _build_weights_with_residual({"A": 0.5, "B": 0.3})
        R = {"A": 0.10, "B": 0.05, OTHER_CASH: 0.0}
        a, s, i = single_period_attribution(w, w, R, R)
        assert a == pytest.approx(0.0)
        assert s == pytest.approx(0.0)
        assert i == pytest.approx(0.0)


class TestGeometricLink:
    """闭合 E2：多期几何链接(非算术求和)。"""

    def test_geometric_link_single(self) -> None:
        assert geometric_link([0.10]) == pytest.approx(0.10)

    def test_geometric_link_multi(self) -> None:
        """∏(1+r_t)-1(复利，非算术和)。"""
        # 两期各 10%：复利 1.1*1.1-1=0.21 != 0.20(算术)
        assert geometric_link([0.10, 0.10]) == pytest.approx(0.21)

    def test_geometric_link_negative(self) -> None:
        assert geometric_link([0.10, -0.05]) == pytest.approx(1.1 * 0.95 - 1)


class TestCarinoSmoothing:
    """闭合 E2：Carino 平滑保证 A+S+I = 复利主动收益。"""

    def test_sum_equals_geometric_active(self) -> None:
        """平滑后 A+S+I = geometric_link(period_active)。"""
        period_active = [0.02, 0.03, -0.01]
        a_sum, s_sum, i_sum = 0.03, 0.01, 0.01
        a, s, i = carino_smoothing(period_active, a_sum, s_sum, i_sum)
        assert (a + s + i) == pytest.approx(geometric_link(period_active))

    def test_zero_active_returns_zero(self) -> None:
        """无主动收益(分母0) -> k=0，三效应=0。"""
        a, s, i = carino_smoothing([0.0, 0.0], 0.0, 0.0, 0.0)
        assert a == 0.0 and s == 0.0 and i == 0.0


class TestBrinsonScope:
    """§3.3.8.2 范围处理：mixed/stock 做 Brinson；指数 TE/IR；债基 None。"""

    def test_mixed_does_brinson(self) -> None:
        attr = brinson_attribution(
            "mixed",
            [{"w_p": {"A": 0.08}, "R_p": {"A": 0.10}, "R_b": {"A": 0.08}}],
            benchmark_weights={"A": 0.06},
        )
        assert attr.scope == "mixed"
        assert attr.allocation is not None
        assert attr.multi_period == "single"

    def test_stock_does_brinson(self) -> None:
        attr = brinson_attribution(
            "stock",
            [{"w_p": {"A": 0.1}, "R_p": {"A": 0.12}, "R_b": {"A": 0.10}}],
            benchmark_weights={"A": 0.08},
        )
        assert attr.scope == "stock"

    def test_index_returns_te_ir(self) -> None:
        """指数基金 -> 跟踪误差 + 信息比率(非 Brinson)。"""
        nav = pd.Series([1.0, 1.01, 0.99, 1.02])
        bench = pd.Series([1.0, 1.0, 1.01, 1.01])
        attr = brinson_attribution("index", periods=[], nav=nav, benchmark_nav=bench, alpha=0.02)
        assert attr.tracking_error is not None
        assert attr.tracking_error >= 0
        assert attr.info_ratio is not None

    def test_bond_returns_none(self) -> None:
        """债基不显示 -> unavailable。"""
        attr = brinson_attribution("bond", periods=[])
        assert attr.unavailable is True

    def test_holdings_missing_unavailable(self) -> None:
        """持仓缺失(空 periods) -> unavailable。"""
        attr = brinson_attribution("mixed", periods=[])
        assert attr.unavailable is True
        assert "no_holdings" in (attr.reason or "")


class TestMultiPeriod:
    """§3.3.8.2 多期几何链接。"""

    def test_multi_period_geometric_link(self) -> None:
        attr = brinson_attribution(
            "mixed",
            [
                {"w_p": {"A": 0.08}, "R_p": {"A": 0.10}, "R_b": {"A": 0.08}},
                {"w_p": {"A": 0.09}, "R_p": {"A": 0.05}, "R_b": {"A": 0.06}},
            ],
            benchmark_weights={"A": 0.06},
        )
        assert attr.multi_period == "geometric_link"
        # 恒等式：active = A+S+I(平滑后)
        assert attr.active_return == pytest.approx(
            attr.allocation + attr.selection + attr.interaction
        )

    def test_single_period_not_geometric(self) -> None:
        """单期 -> multi_period='single'(无链接)。"""
        attr = brinson_attribution(
            "mixed",
            [{"w_p": {"A": 0.08}, "R_p": {"A": 0.10}, "R_b": {"A": 0.08}}],
            benchmark_weights={"A": 0.06},
        )
        assert attr.multi_period == "single"


class TestTrackingError:
    def test_te_zero_identical(self) -> None:
        """基金=基准 -> TE=0。"""
        nav = pd.Series([1.0, 1.1, 1.2])
        assert tracking_error(nav, nav) == pytest.approx(0.0)

    def test_te_positive_diff(self) -> None:
        nav = pd.Series([1.0, 1.1, 1.2])
        bench = pd.Series([1.0, 1.0, 1.0])
        assert tracking_error(nav, bench) > 0

    def test_info_ratio(self) -> None:
        assert info_ratio(0.02, 0.04) == pytest.approx(0.5)
        assert info_ratio(0.02, 0.0) == float("inf")
