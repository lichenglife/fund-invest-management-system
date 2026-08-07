"""风格箱九宫格单测(P1-03b，详设§3.3.1 / TP-01 §3.5 / 闭合 E13 / DC-003)。

覆盖：E13 类型过滤(债/货/QDII 不显示)、持仓法 size/value_growth 分类、
PE≤0 与 growth 越界剔除(E7 对齐)、收益回归交叉验证(一致/不一致/不显著/无因子/样本不足)、
回退链(基金披露风格 is_proxy / 持仓基本面缺失 / 无持仓)、基准回退、守卫。
"""

from __future__ import annotations

import numpy as np
import pytest

import domain.stylebox as sb_mod
from domain.stylebox import (
    GROWTH_HIGH,
    GROWTH_LOW,
    LARGE_CAP_MIN,
    MID_CAP_MIN,
    SIZE_LARGE,
    SIZE_MID,
    SIZE_SMALL,
    STYLEBOX_SCOPE,
    VG_BALANCED,
    VG_GROWTH,
    VG_VALUE,
    style_box,
)

# ---------------------------------------------------------------------------
# 持仓工厂
# ---------------------------------------------------------------------------


def _holdings_large_growth() -> list[dict[str, object]]:
    """大盘成长：加权市值 1750(>=LARGE_CAP_MIN)，加权增速 29(>=GROWTH_HIGH)。"""
    return [
        {"stock": "A", "weight": 0.5, "market_cap": 2000.0, "pe": 40.0, "growth": 30.0},
        {"stock": "B", "weight": 0.5, "market_cap": 1500.0, "pe": 35.0, "growth": 28.0},
    ]


def _holdings_small_value() -> list[dict[str, object]]:
    """小盘价值：加权市值 130(<MID_CAP_MIN)，加权增速 4.2(<=GROWTH_LOW)。"""
    return [
        {"stock": "C", "weight": 0.6, "market_cap": 150.0, "pe": 8.0, "growth": 5.0},
        {"stock": "D", "weight": 0.4, "market_cap": 100.0, "pe": 6.0, "growth": 3.0},
    ]


def _holdings_mid_balanced() -> list[dict[str, object]]:
    """中盘平衡：加权市值 375(中盘)，加权增速 16(GROWTH_LOW<16<GROWTH_HIGH)。"""
    return [
        {"stock": "E", "weight": 0.5, "market_cap": 400.0, "pe": 20.0, "growth": 15.0},
        {"stock": "F", "weight": 0.5, "market_cap": 350.0, "pe": 18.0, "growth": 17.0},
    ]


def _factor_series(
    n: int, beta_v: float, beta_g: float, alpha: float = 0.01, seed: int = 42
) -> tuple[list[float], dict[str, list[float]]]:
    """构造 fund_ret = α + βv·value + βg·growth + 微扰(使 t 有限且显著)。

    微扰极小 -> 显著性由载荷量级 + t(大) 决定；同 seed 可复现。
    """
    rng = np.random.default_rng(seed)
    vf = rng.normal(0.0, 0.01, n).tolist()
    gf = rng.normal(0.0, 0.01, n).tolist()
    noise = rng.normal(0.0, 1e-4, n)
    fund = [
        alpha + beta_v * v + beta_g * g + float(noise[i])
        for i, (v, g) in enumerate(zip(vf, gf, strict=False))
    ]
    return fund, {"value": vf, "growth": gf}


# ---------------------------------------------------------------------------
# E13：类型过滤
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fund_type", ["bond", "money", "qdii"])
def test_non_equity_type_not_applicable(fund_type: str) -> None:
    """E13：债/货/QDII 不显示风格箱 -> available=False。"""
    result = style_box(fund_type, _holdings_large_growth())
    assert result.available is False
    assert result.method == "type_not_applicable"
    assert result.size is None
    assert result.value_growth is None


@pytest.mark.parametrize("fund_type", STYLEBOX_SCOPE)
def test_equity_scope_includes(fund_type: str) -> None:
    """权益类(stock/mixed/index/etf)进入风格箱计算(E13)。"""
    result = style_box(fund_type, _holdings_large_growth())
    assert result.method != "type_not_applicable"


# ---------------------------------------------------------------------------
# 持仓法：两轴分类
# ---------------------------------------------------------------------------


def test_holdings_large_growth() -> None:
    """大盘成长：size=大盘, value_growth=成长, available=True。"""
    result = style_box("mixed", _holdings_large_growth())
    assert result.available is True
    assert result.size == SIZE_LARGE
    assert result.value_growth == VG_GROWTH
    assert result.method == "holdings"
    assert result.is_proxy is False
    # 透明披露中间量
    assert result.metrics["weighted_market_cap"] == pytest.approx(1750.0)
    assert result.metrics["weighted_growth"] == pytest.approx(29.0)
    assert result.metrics["weighted_pe"] == pytest.approx(37.5)


def test_holdings_small_value() -> None:
    result = style_box("stock", _holdings_small_value())
    assert result.available is True
    assert result.size == SIZE_SMALL
    assert result.value_growth == VG_VALUE


def test_holdings_mid_balanced() -> None:
    result = style_box("mixed", _holdings_mid_balanced())
    assert result.available is True
    assert result.size == SIZE_MID
    assert result.value_growth == VG_BALANCED


def test_size_boundary_large_min() -> None:
    """加权市值恰 = LARGE_CAP_MIN -> 大盘(>=)。"""
    holdings = [
        {"stock": "X", "weight": 1.0, "market_cap": LARGE_CAP_MIN, "pe": 20.0, "growth": 15.0}
    ]
    assert style_box("mixed", holdings).size == SIZE_LARGE


def test_size_boundary_mid_min() -> None:
    """加权市值恰 = MID_CAP_MIN -> 中盘。"""
    holdings = [
        {"stock": "X", "weight": 1.0, "market_cap": MID_CAP_MIN, "pe": 20.0, "growth": 15.0}
    ]
    assert style_box("mixed", holdings).size == SIZE_MID


def test_value_growth_boundary_high() -> None:
    """加权增速恰 = GROWTH_HIGH -> 成长(>=)。"""
    holdings = [
        {"stock": "X", "weight": 1.0, "market_cap": 500.0, "pe": 30.0, "growth": GROWTH_HIGH}
    ]
    assert style_box("mixed", holdings).value_growth == VG_GROWTH


def test_value_growth_boundary_low() -> None:
    """加权增速恰 = GROWTH_LOW -> 价值(<=)。"""
    holdings = [
        {"stock": "X", "weight": 1.0, "market_cap": 500.0, "pe": 10.0, "growth": GROWTH_LOW}
    ]
    assert style_box("mixed", holdings).value_growth == VG_VALUE


# ---------------------------------------------------------------------------
# E7 对齐：PE≤0 / growth 越界剔除
# ---------------------------------------------------------------------------


def test_pe_le_zero_excluded() -> None:
    """PE≤0(亏损)个股剔除(对齐 PEG E7)，不置 0。"""
    holdings = [
        {"stock": "G", "weight": 0.5, "market_cap": 500.0, "pe": -5.0, "growth": 20.0},  # PE≤0 剔除
        {"stock": "H", "weight": 0.5, "market_cap": 500.0, "pe": 40.0, "growth": 20.0},
    ]
    result = style_box("mixed", holdings)
    assert result.metrics["weighted_pe"] == pytest.approx(40.0)  # 仅 H
    assert result.metrics["weighted_growth"] == pytest.approx(20.0)


def test_growth_out_of_bound_excluded() -> None:
    """growth 越界(>=100)剔除(对齐 PEG E7)。"""
    holdings = [
        {"stock": "I", "weight": 0.5, "market_cap": 500.0, "pe": 20.0, "growth": 150.0},  # 越界剔除
        {"stock": "J", "weight": 0.5, "market_cap": 500.0, "pe": 20.0, "growth": 20.0},
    ]
    result = style_box("mixed", holdings)
    assert result.metrics["weighted_growth"] == pytest.approx(20.0)  # 仅 J


# ---------------------------------------------------------------------------
# 回退链
# ---------------------------------------------------------------------------


def test_holdings_fundamentals_missing() -> None:
    """持仓在但缺 market_cap/pe/growth -> available=False(不硬算)。"""
    holdings = [
        {"stock": "K", "weight": 0.5, "stock_name": "K"},
        {"stock": "L", "weight": 0.5, "stock_name": "L"},
    ]
    result = style_box("mixed", holdings)
    assert result.available is False
    assert result.method == "holdings_fundamentals_missing"


def test_holdings_missing() -> None:
    """无持仓 -> available=False, method=holdings_missing。"""
    result = style_box("mixed", None)
    assert result.available is False
    assert result.method == "holdings_missing"


def test_benchmark_fallback_when_holdings_missing() -> None:
    """持仓缺失 -> 回退跟踪基准(对齐 PEG/ERP)。"""
    bench = _holdings_large_growth()
    result = style_box("mixed", None, benchmark_holdings=bench)
    assert result.available is True
    assert result.size == SIZE_LARGE
    assert result.source == "benchmark_fallback"


def test_fund_declared_style_fallback() -> None:
    """持仓缺基本面 + 基金披露风格 -> 解析两轴, is_proxy=True。"""
    result = style_box("mixed", [{"stock": "K", "weight": 1.0}], fund_style="大盘价值")
    assert result.available is True
    assert result.size == SIZE_LARGE
    assert result.value_growth == VG_VALUE
    assert result.method == "fund_declared"
    assert result.is_proxy is True
    assert result.source == "fund_declared_style"


def test_fund_declared_style_with_space() -> None:
    """披露风格带空格"中盘 平衡"也能解析。"""
    result = style_box("mixed", None, fund_style="中盘 平衡")
    assert result.size == SIZE_MID
    assert result.value_growth == VG_BALANCED
    assert result.is_proxy is True


def test_holdings_method_takes_precedence_over_declared() -> None:
    """持仓法可得时优先于披露风格(主口径)。"""
    result = style_box("mixed", _holdings_large_growth(), fund_style="小盘价值")
    assert result.method == "holdings"
    assert result.size == SIZE_LARGE  # 持仓法口径，非披露
    assert result.is_proxy is False


# ---------------------------------------------------------------------------
# 收益回归交叉验证(§3.5 / E13)
# ---------------------------------------------------------------------------


def test_regression_none_when_factors_missing() -> None:
    """无因子收益 -> cv_flag=None(未做回归)。"""
    result = style_box("mixed", _holdings_large_growth())
    assert result.cv_flag is None
    assert result.reg_window == "3y"


def test_regression_consistent() -> None:
    """持仓法=成长，回归 growth 载荷 dominant -> 一致 cv_flag=False。"""
    holdings = _holdings_large_growth()  # value_growth=成长
    fund_ret, factors = _factor_series(60, beta_v=0.4, beta_g=0.6)  # growth dominant
    result = style_box("mixed", holdings, factor_returns=factors, fund_returns=fund_ret)
    assert result.cv_flag is False
    assert result.metrics["reg_implied"] == VG_GROWTH


def test_regression_inconsistent() -> None:
    """持仓法=成长，回归 value 载荷 dominant -> 不一致 cv_flag=True。"""
    holdings = _holdings_large_growth()  # value_growth=成长
    fund_ret, factors = _factor_series(60, beta_v=0.6, beta_g=0.4)  # value dominant(均显著)
    result = style_box("mixed", holdings, factor_returns=factors, fund_returns=fund_ret)
    assert result.cv_flag is True
    assert result.metrics["reg_implied"] == VG_VALUE


def test_regression_insignificant_load() -> None:
    """growth 载荷 |load|<0.3 -> 不显著 cv_flag=True(E13)。"""
    holdings = _holdings_large_growth()
    fund_ret, factors = _factor_series(60, beta_v=0.5, beta_g=0.2)  # beta_g<0.3
    result = style_box("mixed", holdings, factor_returns=factors, fund_returns=fund_ret)
    assert result.cv_flag is True


def test_regression_insufficient_sample() -> None:
    """样本不足(<=3) -> 不可回归 cv_flag=None。"""
    holdings = _holdings_large_growth()
    fund_ret, factors = _factor_series(3, beta_v=0.4, beta_g=0.6)
    result = style_box("mixed", holdings, factor_returns=factors, fund_returns=fund_ret)
    assert result.cv_flag is None
    assert result.metrics["regression"] == "insufficient_sample"


# ---------------------------------------------------------------------------
# 守卫
# ---------------------------------------------------------------------------


def test_guard_blocks_when_caliber_undefined(monkeypatch: pytest.MonkeyPatch) -> None:
    """守卫未定义口径 -> 一律 None(§3.3.7 语义)。"""
    monkeypatch.setattr(sb_mod, "_guard_passed", lambda: False)
    result = style_box("mixed", _holdings_large_growth(), guard=True)
    assert result.available is False
    assert result.method == "guard_blocked"


def test_guard_disabled_bypasses() -> None:
    """守卫关闭时不拦截(直接计算)。"""
    # _guard_passed 仍返 True；显式 guard=False 也应正常计算
    result = style_box("mixed", _holdings_large_growth(), guard=False)
    assert result.available is True


# ---------------------------------------------------------------------------
# to_dict
# ---------------------------------------------------------------------------


def test_to_dict_contract() -> None:
    """to_dict 含 §3.3.6 契约键 + 透明中间量。"""
    result = style_box("mixed", _holdings_large_growth())
    d = result.to_dict()
    for key in (
        "size",
        "value_growth",
        "available",
        "cv_flag",
        "method",
        "reg_window",
        "is_proxy",
        "as_of",
        "source",
        "metrics",
    ):
        assert key in d
    assert d["available"] is True
