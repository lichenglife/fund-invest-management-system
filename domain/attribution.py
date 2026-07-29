"""Brinson 业绩归因(P1-03c，详设§3.3.8.2 / TP-01 §3.3 / DC-003 / CLAUDE.md §4 红线 E1/E2)。

仅 ``BRINSON_SCOPE=["mixed","stock"]`` 主动股混基做 Brinson(§3.3.8.2)。
指数/ETF 改显跟踪误差 TE + 信息比率 IR；债基不显示(返 None)。

三向分解(单期，§3.3.8.2)：
    Allocation  = Σ_i (w_p,i − w_b,i) · R_b,i     # 配置效应(i 含 OTHER_CASH 桶)
    Selection   = Σ_i w_b,i · (R_p,i − R_b,i)     # 选券效应
    Interaction = Σ_i (w_p,i − w_b,i) · (R_p,i − R_b,i)  # 交互效应
    ActiveReturn = Allocation + Selection + Interaction

多期链接(闭合 E2)：各期主动收益**几何链接** ∏(1+r_t)−1 得复利主动收益，
再按 Carino/Frongello 平滑系数 ``k = total_active / (A_sum+S_sum+I_sum)`` 分配，
保证三效应之和 = 复利主动收益(非算术求和)。

权重处理(闭合 E1)：用**披露真实权重**(和<1，严禁归一化)，未披露部分归入
``OTHER_CASH`` 残差桶(``w_p,other = 1 − Σ 已披露``)，基准端同样设残差桶匹配。
持仓缺失 -> ``unavailable=True``。
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

#: 仅主动股混基做 Brinson(§3.3.8.2 / DC-003)。
BRINSON_SCOPE: list[str] = ["mixed", "stock"]

#: 残差桶标识(基金/基准各设，闭合 E1)。
OTHER_CASH = "OTHER_CASH"


@dataclass(frozen=True)
class Attribution:
    """Brinson 归因结果(§3.3.8.2 / 对齐 §2.21 attribution 响应)。

    Attributes:
        allocation: 配置效应(几何链接后)。
        selection: 选券效应。
        interaction: 交互效应。
        active_return: 主动收益 = A+S+I(复利口径)。
        scope: 适用范围(mixed/stock)。
        multi_period: 多期口径(geometric_link 或 single)。
        unavailable: 持仓/基准缺失时 True。
        reason: 不可用原因。
        tracking_error: 指数基金跟踪误差(非 Brinson)。
        info_ratio: 指数基金信息比率。
    """

    allocation: float | None = None
    selection: float | None = None
    interaction: float | None = None
    active_return: float | None = None
    scope: str | None = None
    multi_period: str | None = None
    unavailable: bool = False
    reason: str | None = None
    tracking_error: float | None = None
    info_ratio: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "allocation": self.allocation,
            "selection": self.selection,
            "interaction": self.interaction,
            "active_return": self.active_return,
            "scope": self.scope,
            "multi_period": self.multi_period,
            "unavailable": self.unavailable,
            "reason": self.reason,
            "tracking_error": self.tracking_error,
            "info_ratio": self.info_ratio,
        }


# ---------------------------------------------------------------------------
# 单期三向分解(E1：真实权重 + OTHER_CASH 残差桶)
# ---------------------------------------------------------------------------


def _build_weights_with_residual(
    disclosed: dict[str, float],
) -> tuple[dict[str, float], float]:
    """构造含 OTHER_CASH 残差桶的权重(闭合 E1)。

    Args:
        disclosed: 披露真实权重(和常<1，不归一化)。
    Returns:
        (含残差的权重 dict, 残差权重)。OTHER_CASH = max(0, 1-Σ已披露)。
    """
    resid = max(0.0, 1.0 - sum(disclosed.values()))
    weights = {**disclosed, OTHER_CASH: resid}
    return weights, resid


def single_period_attribution(
    w_p: dict[str, float],
    w_b: dict[str, float],
    R_p: dict[str, float],
    R_b: dict[str, float],
) -> tuple[float, float, float]:
    """单期三向分解(§3.3.8.2)。

    i 遍历基金与基准权重的并集(含 OTHER_CASH 桶)；缺失权重/收益按 0。
    返回 (Allocation, Selection, Interaction)。
    """
    assets = set(w_p) | set(w_b)
    a = sum((w_p.get(i, 0.0) - w_b.get(i, 0.0)) * R_b.get(i, 0.0) for i in assets)
    s = sum(w_b.get(i, 0.0) * (R_p.get(i, 0.0) - R_b.get(i, 0.0)) for i in assets)
    inter = sum(
        (w_p.get(i, 0.0) - w_b.get(i, 0.0)) * (R_p.get(i, 0.0) - R_b.get(i, 0.0)) for i in assets
    )
    return a, s, inter


# ---------------------------------------------------------------------------
# 多期几何链接(闭合 E2)
# ---------------------------------------------------------------------------


def geometric_link(period_returns: list[float]) -> float:
    """几何链接：∏(1+r_t)−1(复利主动收益，闭合 E2)。

    Args:
        period_returns: 各期主动收益(单期 A+S+I)。
    Returns:
        复利总主动收益。
    """
    prod = 1.0
    for r in period_returns:
        prod *= 1.0 + r
    return prod - 1.0


def carino_smoothing(
    period_active: list[float], a_sum: float, s_sum: float, i_sum: float
) -> tuple[float, float, float]:
    """Carino/Frongello 平滑：三效应按 k 折算到复利主动收益(闭合 E2)。

    k = total_active / (A_sum+S_sum+I_sum)；保证 A+S+I(平滑后) = 复利主动收益。
    分母为 0(无主动收益)时 k=0。
    """
    total_active = geometric_link(period_active)
    denom = a_sum + s_sum + i_sum
    k = total_active / denom if denom != 0 else 0.0
    return a_sum * k, s_sum * k, i_sum * k


# ---------------------------------------------------------------------------
# 跟踪误差/信息比率(指数基金，§3.3.8.2 范围处理)
# ---------------------------------------------------------------------------


def tracking_error(nav: pd.Series, benchmark: pd.Series, periods: int = 250) -> float:
    """跟踪误差(年化，§3.3.8.2 指数基金用)。

    = std(基金收益 − 基准收益) * sqrt(periods)。
    """
    diff = nav.pct_change() - benchmark.pct_change()
    diff = diff.dropna()
    if len(diff) < 2:
        return 0.0
    return float(diff.std() * math.sqrt(periods))


def info_ratio(alpha: float, te: float) -> float:
    """信息比率 = alpha / TE(§3.3.8.2)。TE=0 时返 inf(无跟踪误差)。"""
    if te == 0:
        return float("inf")
    return alpha / te


# ---------------------------------------------------------------------------
# Brinson 归因主入口
# ---------------------------------------------------------------------------


def brinson_attribution(
    fund_type: str,
    periods: list[dict[str, Any]],
    *,
    benchmark_weights: dict[str, float] | None = None,
    nav: pd.Series | None = None,
    benchmark_nav: pd.Series | None = None,
    alpha: float | None = None,
) -> Attribution:
    """Brinson 业绩归因(§3.3.8.2 / TP-01 §3.3)。

    Args:
        fund_type: 基金类型(决定是否在 BRINSON_SCOPE)。
        periods: 各持仓报告期数据，每项：
            ``{"w_p": 披露权重dict, "R_p": 基金各层收益dict, "R_b": 基准各层收益dict}``。
            w_p 用披露真实权重(和<1，不归一化)。
        benchmark_weights: 基准成分权重(用于基准残差桶)；None 时基准残差=1-Σperiod基准权重。
        nav: 基金净值(指数基金算 TE/IR 用)。
        benchmark_nav: 基准净值(算 TE 用)。
        alpha: 超额收益(算 IR 用)。
    Returns:
        Attribution：主动股混基 -> 三向分解；指数 -> TE/IR；债基 -> None。
    """
    # 范围处理(§3.3.8.2)
    if fund_type not in BRINSON_SCOPE:
        if fund_type in ("index", "etf"):
            # 指数/ETF：改显 TE + IR
            te = (
                tracking_error(nav, benchmark_nav)
                if (nav is not None and benchmark_nav is not None)
                else None
            )
            ir = info_ratio(alpha, te) if (alpha is not None and te is not None) else None
            return Attribution(tracking_error=te, info_ratio=ir, scope=fund_type, unavailable=False)
        # 债基等不显示
        return Attribution(unavailable=True, reason=f"fund_type {fund_type} not in Brinson scope")

    if not periods:
        return Attribution(unavailable=True, reason="no_holdings_periods", scope=fund_type)

    # 基准残差桶(闭合 E1)
    bench_w: dict[str, float] = benchmark_weights or {}
    bench_w_p, _ = _build_weights_with_residual(bench_w)

    a_sum = s_sum = i_sum = 0.0
    period_active: list[float] = []
    for p in periods:
        # 基金端：披露真实权重 + OTHER_CASH 残差(闭合 E1，不归一化)
        w_p, _ = _build_weights_with_residual(p.get("w_p", {}))
        w_b = bench_w_p  # 基准权重各期一致(含残差桶)
        R_p = {**p.get("R_p", {}), OTHER_CASH: p.get("cash_return", 0.0)}
        R_b = {**p.get("R_b", {}), OTHER_CASH: p.get("cash_return", 0.0)}
        a, s, inter = single_period_attribution(w_p, w_b, R_p, R_b)
        a_sum += a
        s_sum += s
        i_sum += inter
        period_active.append(a + s + inter)

    # 多期几何链接 + Carino 平滑(闭合 E2)
    if len(periods) == 1:
        # 单期：直接用 A/S/I(无链接)
        return Attribution(
            allocation=a_sum,
            selection=s_sum,
            interaction=i_sum,
            active_return=a_sum + s_sum + i_sum,
            scope=fund_type,
            multi_period="single",
        )
    a, s, inter = carino_smoothing(period_active, a_sum, s_sum, i_sum)
    return Attribution(
        allocation=a,
        selection=s,
        interaction=inter,
        active_return=a + s + inter,  # 平滑后 = 复利主动收益(§3.3.8.2)
        scope=fund_type,
        multi_period="geometric_link",
    )


__all__: list[str] = [
    "BRINSON_SCOPE",
    "OTHER_CASH",
    "Attribution",
    "single_period_attribution",
    "geometric_link",
    "carino_smoothing",
    "tracking_error",
    "info_ratio",
    "brinson_attribution",
]
