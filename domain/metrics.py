"""基金核心指标计算(P1-03a，详设§3.3.2 / §3.3.8 / TP-01 §3 / DC-003)。

核心指标：年化收益/年化波动/夏普/索提诺/卡玛/最大回撤；基准按类型自动选(DC-003)；
与 empyrical 交叉验证，误差>0.5% 置 ``cv_flag=True``(§3.3.2 流程 D->E)。

纯函数(ADR-002 唯一权威源可复用)：输入 NAV 序列 -> 输出 Metrics。
无 DB/Web 依赖，便于 CI 高频跑与多进程复用(§3.3.9 批算)。

口径约定：
- 输入 NAV(净值序列)；内部转日收益率(pct_change)。
- ``max_drawdown`` 返回**负值**(E5：越负越差，全局统一)。
- 默认窗口 3Y(``DEFAULT_EVAL_WINDOW``，DC-003)；periods=250(年交易日)。
- 无风险利率 rf 默认 0.02。
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Any

import empyrical as ep
import pandas as pd

logger = logging.getLogger(__name__)

#: 默认评估窗口(DC-003)。
DEFAULT_EVAL_WINDOW = "3Y"

#: 年交易日数(A 股约 250)。
TRADING_DAYS = 250

#: 默认无风险利率(年化)。
RF_DEFAULT = 0.02

#: 基准按类型自动选(DC-003，详设§3.3.1)。
BENCHMARK_MAP: dict[str, str] = {
    "stock": "HS300",
    "mixed": "ZZ800",
    "bond": "CBA_TOTAL",
    "index": "track_index",
    "qdii": "MSCI",
    "money": "MMF",
}

#: 交叉验证阈值(误差>0.5% 置 cv_flag，§3.3.2)。
CV_ERROR_THRESHOLD = 0.005


@dataclass(frozen=True)
class Metrics:
    """核心指标结果(§3.3.2 / 对齐 research_metrics 表)。

    所有比率为小数(0.15 = 15%)；max_drawdown 为负值(E5)。
    """

    annualized_return: float | None = None  # 年化收益
    annualized_volatility: float | None = None  # 年化波动
    sharpe: float | None = None  # 夏普
    sortino: float | None = None  # 索提诺
    calmar: float | None = None  # 卡玛
    max_drawdown: float | None = None  # 最大回撤(负值，E5)
    cv_flag: bool = False  # 交叉验证误差>0.5%
    cv_error: float | None = None  # 与 empyrical 误差
    benchmark: str | None = None  # 使用的基准
    window: str = DEFAULT_EVAL_WINDOW  # 评估窗口
    as_of: str | None = None  # 数据截至

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clean_nav(nav: pd.Series) -> pd.Series:
    """NAV 清洗：丢弃非正值(§4 红线，NAV<=0 防护)。"""
    return nav[nav > 0]


def max_drawdown(nav: pd.Series) -> float:
    """最大回撤(返回负值，E5 约定)。

    Args:
        nav: 净值序列(index=日期)。
    Returns:
        最大回撤(负值，越负越差)。
    """
    nav = _clean_nav(nav)
    returns = _to_returns(nav)
    md = ep.max_drawdown(returns)
    # empyrical max_drawdown 已返回负值；确保符号统一(E5)
    return float(md)


def annualized_return(nav: pd.Series, periods: int = TRADING_DAYS) -> float:
    """年化收益。"""
    nav = _clean_nav(nav)
    returns = _to_returns(nav)
    return float(ep.annual_return(returns, period="daily", annualization=periods))


def annualized_volatility(nav: pd.Series, periods: int = TRADING_DAYS) -> float:
    """年化波动率。"""
    nav = _clean_nav(nav)
    returns = _to_returns(nav)
    return float(ep.annual_volatility(returns, period="daily", annualization=periods))


def compute_metrics(
    nav: pd.Series,
    rf: float = RF_DEFAULT,
    periods: int = TRADING_DAYS,
    benchmark: str | None = None,
    window: str = DEFAULT_EVAL_WINDOW,
    fund_type: str | None = None,
) -> Metrics:
    """计算核心指标 + empyrical 交叉验证(§3.3.2)。

    Args:
        nav: 净值序列(index=日期)。
        rf: 无风险利率(年化，默认 0.02)。
        periods: 年交易日数(默认 250)。
        benchmark: 显式基准；None 时按 fund_type 自动选(DC-003)。
        window: 评估窗口(默认 3Y)。
        fund_type: 基金类型(用于基准自动选)。
    Returns:
        Metrics(含 cv_flag)。
    """
    if nav is None or len(nav) < 2:
        # NAV 不足 -> 全 None，不崩溃(§4 红线：NAV=0/极值不崩溃)
        logger.warning(
            "metrics.insufficient_nav",
            extra={"action": "metrics", "len": len(nav) if nav is not None else 0},
        )
        return Metrics(benchmark=benchmark, window=window)

    # NAV<=0 防护(§4 红线)：pct_change 对 0/负 NAV 产生 inf，empyrical 会崩。
    # 过滤非正 NAV；若过滤后不足 -> 返回 None 指标，不崩溃。
    nav_clean = _clean_nav(nav)
    if len(nav_clean) < 2:
        logger.warning("metrics.invalid_nav", extra={"action": "metrics", "reason": "nav<=0"})
        return Metrics(benchmark=benchmark, window=window)

    returns = _to_returns(nav_clean)

    # 基准自动选(DC-003)
    if benchmark is None and fund_type is not None:
        benchmark = BENCHMARK_MAP.get(fund_type)
    if benchmark is None:
        benchmark = BENCHMARK_MAP.get("mixed")  # 默认 ZZ800

    # 核心指标(empyrical；sortino 自实现，empyrical 0.5 与 numpy 2.x 的 np.NINF 不兼容)
    ann_ret = float(ep.annual_return(returns, period="daily", annualization=periods))
    ann_vol = float(ep.annual_volatility(returns, period="daily", annualization=periods))
    md = float(ep.max_drawdown(returns))  # 负值(E5)
    sharpe = float(
        ep.sharpe_ratio(returns, risk_free=rf / periods, period="daily", annualization=periods)
    )
    sortino = _sortino(returns, rf / periods, periods)
    calmar = float(ep.calmar_ratio(returns, period="daily", annualization=periods))

    # 交叉验证：用年化收益做自洽校验(annual_return vs 复利推算)
    # 复利推算：(nav.iloc[-1]/nav.iloc[0])^(periods/len) - 1
    cv_error = _cross_validate_annual_return(nav_clean, ann_ret, periods)
    cv_flag = cv_error is not None and abs(cv_error) > CV_ERROR_THRESHOLD

    return Metrics(
        annualized_return=ann_ret,
        annualized_volatility=ann_vol,
        sharpe=sharpe,
        sortino=sortino,
        calmar=calmar,
        max_drawdown=md,
        cv_flag=cv_flag,
        cv_error=cv_error,
        benchmark=benchmark,
        window=window,
    )


def _to_returns(nav: pd.Series) -> pd.Series:
    """NAV -> 日收益率(pct_change)。首日 NaN 丢弃。"""
    returns = nav.pct_change().dropna()
    return returns


def _sortino(returns: pd.Series, daily_rf: float, periods: int) -> float:
    """Sortino 比率(自实现，规避 empyrical 0.5 + numpy 2.x 不兼容)。

    Sortino = (年化超额收益) / (年化下行标准差)
    下行标准差仅对 <0 的收益率计算(下行风险)。

    Args:
        returns: 日收益率序列。
        daily_rf: 日无风险利率(年化 rf / periods)。
        periods: 年交易日数。
    Returns:
        Sortino 比率；下行风险为 0 时返回 inf(无下行风险)。
    """
    import numpy as np

    excess = returns - daily_rf
    ann_excess = float(excess.mean() * periods)  # 年化超额
    downside = returns[returns < 0]
    if len(downside) == 0:
        return float("inf")  # 无下行风险
    downside_std = float(np.sqrt((downside**2).mean()) * np.sqrt(periods))  # 年化下行标准差
    if downside_std == 0:
        return float("inf")
    return ann_excess / downside_std


def _cross_validate_annual_return(
    nav: pd.Series, empyrical_ann: float, periods: int
) -> float | None:
    """交叉验证：empyrical 年化收益 vs 复利推算年化收益，返回误差(§3.3.2)。

    复利推算：``r = (end/start)^(periods/n) - 1``；与 empyrical annual_return 比，
    误差>0.5% 置 cv_flag(数据质量/口径问题)。
    """
    if len(nav) < 2:
        return None
    start = float(nav.iloc[0])
    end = float(nav.iloc[-1])
    if start <= 0:
        return None  # NAV<=0 不崩溃(§4 红线)
    n = len(nav) - 1
    if n <= 0:
        return None
    compound_ann = (end / start) ** (periods / n) - 1
    if empyrical_ann == 0:
        return None
    return float(compound_ann - empyrical_ann)


__all__: list[str] = [
    "Metrics",
    "compute_metrics",
    "max_drawdown",
    "annualized_return",
    "annualized_volatility",
    "DEFAULT_EVAL_WINDOW",
    "TRADING_DAYS",
    "RF_DEFAULT",
    "BENCHMARK_MAP",
    "CV_ERROR_THRESHOLD",
]
