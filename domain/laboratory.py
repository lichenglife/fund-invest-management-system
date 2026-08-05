"""单基深度实验室(P1-09a，详设§3.8 / DC-011 / FR-40~42)。

把评估变推演：回本测算 + 三情景推演 + 五策略对照。

口径(§3.8.2)：
- 回本需涨 = ``abs(r)/(1+r)``(r 为当前收益率；r>=0 已盈利；r<=-1 净值归零不可回本)。
- 三情景：保守/基准/乐观 年化假设 -> 投影 N 月净值 + 回本所需月数。
- 五策略对照：持有/定投/波段/调仓/止损 -> 同窗口终值与收益对比。

> 输入收益率来自数据中心真实净值(§3.8.6 OQ-25，禁止编造)；本模块为纯算法，nav 由调用方注入。
> 复用 ``domain.backtest_dca.run_dca`` 做定投策略(§3.8.2 联动)。
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

#: 三情景年化假设(§3.8.2；可配，默认 A 股权益合理区间)。
SCENARIO_ASSUMPTIONS: dict[str, float] = {
    "conservative": -0.10,  # 保守 -10%/年
    "baseline": 0.08,  # 基准 +8%/年(长期权益中枢)
    "optimistic": 0.20,  # 乐观 +20%/年
}

#: 三情景月化(由年化折算)。
SCENARIO_MONTHLY: dict[str, float] = {
    k: (1.0 + v) ** (1.0 / 12.0) - 1.0 for k, v in SCENARIO_ASSUMPTIONS.items()
}

#: 默认投影月数。
DEFAULT_PROJECTION_MONTHS = 12

#: 五策略标识(§3.8.2)。
STRATEGIES = ["hold", "dca", "swing", "rebalance", "stop_loss"]

#: 策略中文名。
STRATEGY_NAMES: dict[str, str] = {
    "hold": "持有",
    "dca": "定投",
    "swing": "波段",
    "rebalance": "调仓",
    "stop_loss": "止损",
}

#: 策略参数。
STRATEGY_PARAMS: dict[str, Any] = {
    "swing_trade_threshold": 0.05,  # 波段：涨/跌 5% 触发
    "stop_loss_threshold": -0.10,  # 止损：-10% 清仓
    "rebalance_freq": "ME",  # 调仓：月频
    "dca_amount": 1000.0,  # 定投：每期金额
}


@dataclass(frozen=True)
class BreakevenResult:
    """回本测算结果(§3.8.2)。"""

    return_rate: float
    breakeven_gain_pct: float | None  # 回本需涨(%)
    profitable: bool
    months_to_breakeven: dict[str, float | None] = field(default_factory=dict)
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "return_rate": self.return_rate,
            "breakeven_gain_pct": self.breakeven_gain_pct,
            "profitable": self.profitable,
            "months_to_breakeven": self.months_to_breakeven,
            "note": self.note,
        }


@dataclass(frozen=True)
class ScenarioResult:
    """三情景推演结果(§3.8.2)。"""

    months: int
    projections: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    assumptions: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "months": self.months,
            "projections": self.projections,
            "assumptions": self.assumptions,
        }


@dataclass(frozen=True)
class StrategyResult:
    """五策略对照结果(§3.8.2)。"""

    strategy: str
    name: str
    final_value: float  # 终值(起点 1.0 基准)
    total_return: float  # 总收益率
    max_drawdown: float  # 最大回撤(负值，E5)
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "name": self.name,
            "final_value": self.final_value,
            "total_return": self.total_return,
            "max_drawdown": self.max_drawdown,
            "note": self.note,
        }


def breakeven_analysis(return_rate: float, *, months: int = DEFAULT_PROJECTION_MONTHS) -> BreakevenResult:
    """回本测算(§3.8.2)。

    Args:
        return_rate: 当前收益率 r(来自真实净值，-1<r；r<=-1 净值归零)。
        months: 投影月数(三情景回本时间用)。
    Returns:
        BreakevenResult。
    """
    r = return_rate
    # r>=0 已盈利
    if r >= 0:
        return BreakevenResult(
            return_rate=r, breakeven_gain_pct=0.0, profitable=True,
            note="已盈利，无需回本",
        )
    # r<=-1 净值归零(§4 不崩溃)
    if r <= -1.0:
        return BreakevenResult(
            return_rate=r, breakeven_gain_pct=None, profitable=False,
            note="净值归零，无法回本",
        )

    # 回本需涨 = abs(r)/(1+r)
    gain = abs(r) / (1.0 + r)

    # 三情景回本所需月数：现值 (1+r)，需涨至 1.0
    # (1+r)*(1+m_monthly)^n = 1.0 -> n = log(1/(1+r)) / log(1+m_monthly)
    months_to: dict[str, float | None] = {}
    target = 1.0 / (1.0 + r)  # 需达到的相对涨幅
    for name, m_monthly in SCENARIO_MONTHLY.items():
        if m_monthly <= 0:
            # 保守情景假设为负 -> 永不回本
            months_to[name] = None
            continue
        try:
            n = math.log(target) / math.log(1.0 + m_monthly)
            months_to[name] = round(n, 1)
        except (ValueError, ZeroDivisionError):
            months_to[name] = None

    return BreakevenResult(
        return_rate=r,
        breakeven_gain_pct=round(gain, 6),
        profitable=False,
        months_to_breakeven=months_to,
        note=f"需涨 {gain*100:.1f}% 回本",
    )


def scenario_projection(
    nav: pd.Series | None, *, months: int = DEFAULT_PROJECTION_MONTHS
) -> ScenarioResult:
    """三情景推演(§3.8.2)。

    基准情景用真实净值历史年化(若有)；保守/乐观用固定假设。
    投影 N 月净值曲线(起点=最新净值)。

    Args:
        nav: 历史后复权净值序列(用于推导基准年化)；None 时基准用默认假设。
        months: 投影月数。
    Returns:
        ScenarioResult。
    """
    assumptions = dict(SCENARIO_ASSUMPTIONS)
    # 基准年化：若有历史净值，用真实年化
    if nav is not None and len(nav) > 1:
        hist_ann = _historical_annual_return(nav)
        if hist_ann is not None:
            assumptions["baseline"] = hist_ann

    projections: dict[str, list[dict[str, Any]]] = {}
    for name, ann in assumptions.items():
        m_monthly = (1.0 + ann) ** (1.0 / 12.0) - 1.0
        curve = []
        for i in range(months + 1):
            value = (1.0 + m_monthly) ** i  # 起点 1.0
            curve.append({"month": i, "value": round(value, 6)})
        projections[name] = curve

    return ScenarioResult(months=months, projections=projections, assumptions=assumptions)


def strategy_comparison(nav: pd.Series) -> list[StrategyResult]:
    """五策略对照(§3.8.2)。

    同一历史净值窗口下，对比五策略终值/收益/回撤。

    Args:
        nav: 历史后复权净值序列(index=日期)。
    Returns:
        五策略 StrategyResult 列表。
    """
    if nav is None or len(nav) < 2:
        return []

    results: list[StrategyResult] = []
    for strat in STRATEGIES:
        results.append(_run_strategy(strat, nav))
    return results


def _run_strategy(strategy: str, nav: pd.Series) -> StrategyResult:
    """执行单策略。"""
    name = STRATEGY_NAMES.get(strategy, strategy)
    if strategy == "hold":
        return _hold_strategy(nav, name)
    if strategy == "dca":
        return _dca_strategy(nav, name)
    if strategy == "swing":
        return _swing_strategy(nav, name)
    if strategy == "rebalance":
        return _rebalance_strategy(nav, name)
    if strategy == "stop_loss":
        return _stop_loss_strategy(nav, name)
    return StrategyResult(strategy, name, 0.0, 0.0, 0.0, "未实现")


def _hold_strategy(nav: pd.Series, name: str) -> StrategyResult:
    """持有：买入持有全窗口。"""
    ret = float(nav.iloc[-1] / nav.iloc[0]) - 1.0
    mdd = _max_drawdown(nav)
    return StrategyResult(
        "hold", name, final_value=round(1.0 + ret, 6),
        total_return=round(ret, 6), max_drawdown=mdd, note="买入持有",
    )


def _dca_strategy(nav: pd.Series, name: str) -> StrategyResult:
    """定投：月频等额定投(复用 run_dca 逻辑)。"""
    from domain.backtest_dca import run_dca

    result = run_dca(nav, freq="monthly", amount=STRATEGY_PARAMS["dca_amount"])
    # 定投收益率 = final_value/cum_invest - 1
    ret = result.final_value / result.cum_invest - 1.0 if result.cum_invest > 0 else 0.0
    return StrategyResult(
        "dca", name, final_value=round(1.0 + ret, 6),
        total_return=round(ret, 6), max_drawdown=result.max_drawdown,
        note=f"月定投{int(STRATEGY_PARAMS['dca_amount'])}元",
    )


def _swing_strategy(nav: pd.Series, name: str) -> StrategyResult:
    """波段：涨/跌超阈值触发买卖(简化：涨5%卖半、跌5%买回)。"""
    threshold = STRATEGY_PARAMS["swing_trade_threshold"]
    position = 1.0  # 满仓
    cash = 0.0
    last_trade_val = float(nav.iloc[0])
    for v in nav:
        v = float(v)
        if v <= 0:
            continue
        change = (v - last_trade_val) / last_trade_val if last_trade_val > 0 else 0.0
        if change >= threshold and position > 0:
            # 涨超阈值 -> 卖半
            cash += position * 0.5 * v
            position *= 0.5
            last_trade_val = v
        elif change <= -threshold and cash > 0:
            # 跌超阈值 -> 用现金买回
            buy = cash / v
            position += buy
            cash = 0.0
            last_trade_val = v
    final = position * float(nav.iloc[-1]) + cash
    ret = final - 1.0
    mdd = _max_drawdown(nav)
    return StrategyResult(
        "swing", name, final_value=round(final, 6),
        total_return=round(ret, 6), max_drawdown=mdd,
        note=f"涨跌{int(threshold*100)}%触发",
    )


def _rebalance_strategy(nav: pd.Series, name: str) -> StrategyResult:
    """调仓：月频再平衡(单基简化为趋势跟踪，跌破均线减仓)。"""
    # 简化：月频检查均线，均线上方满仓，下方半仓
    monthly = nav.resample(STRATEGY_PARAMS["rebalance_freq"]).last().dropna()
    if len(monthly) < 2:
        return _hold_strategy(nav, name)
    ma = monthly.rolling(window=min(3, len(monthly)), min_periods=1).mean()
    position = 1.0
    for i in range(1, len(monthly)):
        v = float(monthly.iloc[i])
        if v <= 0:
            continue
        position = 1.0 if v > float(ma.iloc[i]) else 0.5  # 均线上方满仓/下方半仓
    ret = position * (float(nav.iloc[-1]) / float(nav.iloc[0]) - 1.0)
    mdd = _max_drawdown(nav)
    return StrategyResult(
        "rebalance", name, final_value=round(1.0 + ret, 6),
        total_return=round(ret, 6), max_drawdown=mdd,
        note="月频均线调仓",
    )


def _stop_loss_strategy(nav: pd.Series, name: str) -> StrategyResult:
    """止损：跌幅超阈值清仓(持有现金至期末)。"""
    threshold = STRATEGY_PARAMS["stop_loss_threshold"]
    entry = float(nav.iloc[0])
    position = 1.0
    cash = 0.0
    for v in nav:
        v = float(v)
        if v <= 0:
            continue
        ret = (v - entry) / entry if entry > 0 else 0.0
        if ret <= threshold and position > 0:
            cash = position * v  # 清仓转现金
            position = 0.0
    final = position * float(nav.iloc[-1]) + cash
    ret = final - 1.0
    mdd = _max_drawdown(nav)
    return StrategyResult(
        "stop_loss", name, final_value=round(final, 6),
        total_return=round(ret, 6), max_drawdown=mdd,
        note=f"跌{int(abs(threshold)*100)}%止损",
    )


def _max_drawdown(nav: pd.Series) -> float:
    """最大回撤(负值，E5)。"""
    if len(nav) < 2:
        return 0.0
    peak = nav.cummax()
    dd = (nav - peak) / peak
    val = float(dd.min())
    return round(val, 6) if not math.isnan(val) else 0.0


def _historical_annual_return(nav: pd.Series) -> float | None:
    """真实年化收益率(几何)。"""
    if len(nav) < 2:
        return None
    start = float(nav.iloc[0])
    end = float(nav.iloc[-1])
    if start <= 0:
        return None
    days = (nav.index[-1] - nav.index[0]).days
    if days <= 0:
        return None
    years = days / 365.25
    if years < 0.01:
        return None
    ann = float((end / start) ** (1.0 / years) - 1.0)
    if math.isfinite(ann):
        return round(ann, 6)
    return None


__all__: list[str] = [
    "SCENARIO_ASSUMPTIONS",
    "STRATEGIES",
    "STRATEGY_NAMES",
    "BreakevenResult",
    "ScenarioResult",
    "StrategyResult",
    "breakeven_analysis",
    "scenario_projection",
    "strategy_comparison",
]
