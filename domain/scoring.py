"""五因子综合评分(P1-03b，详设§3.3.8.1 / TP-01 §3.1 / DC-003 / CLAUDE.md §4 红线)。

五因子 ``ret/risk/perf/scale/manager``，权重 ``SCORE_WEIGHTS={ret:20,risk:25,perf:20,
scale:15,manager:20}``(E4/E5 闭环，ret 降共线权重)。

子分归一化：横截面按 ``asset_class`` 分组百分位(该基金在同类 universe 百分位×100，E5)；
可选 z-score+Sigmoid。缺失因子 ``s_k=None``，合成时剔除该因子权重(分母随之缩小)。

综合分：``composite = Σ(w_k·s_k) / Σ w_k``(仅有效因子，0-100)，返回各 ``s_k`` 与贡献
``w_k·s_k``(因子分解)。前端滑杆调权后按此式即时重算(ADR-002 唯一权威源)。

口径红线(§4)：
- scale -> ``scale_health``：非线性(aum∈[2亿,500亿]=100；<2亿清盘风险缓降；>500亿钝化缓降，E4)。
- manager -> ``manager_excess``：=任期区间基金收益−同类基准收益，**任期超额非能力归因**，须标注。
- 货基(money)收益/回撤恒近0，**排除综合分排名**，单独呈现(E5)。
- max_drawdown 返回负值(E5，越负越差 -> 子分越低)。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from domain.metrics import annualized_return, max_drawdown

logger = logging.getLogger(__name__)

#: 五因子权重(E4/E5 闭环，详设§3.3.8.1)。ret 降共线权重至 20。
SCORE_WEIGHTS: dict[str, int] = {"ret": 20, "risk": 25, "perf": 20, "scale": 15, "manager": 20}

#: 五因子顺序(对外展示稳定)。
FACTOR_ORDER: list[str] = ["ret", "risk", "perf", "scale", "manager"]

#: scale_health 阈值(亿元，E4)。
SCALE_HEALTHY_MIN = 2.0  # <2亿 触发清盘风险
SCALE_HEALTHY_MAX = 500.0  # >500亿 钝化

#: 货基排除综合分排名(E5)。
MONEY_EXCLUDED = "money"


@dataclass(frozen=True)
class FactorScore:
    """单因子子分与贡献(因子分解，§3.3.8.1)。

    Attributes:
        name: 因子名(ret/risk/perf/scale/manager)。
        sub_score: 0-100 子分(横截面百分位)；None 表示缺失。
        weight: 因子权重(SCORE_WEIGHTS)。
        raw: 原始指标值(年化收益/回撤/aum 等，溯源用)。
        contrib: 贡献 = weight * sub_score(合成用)；sub_score 缺失时为 None。
    """

    name: str
    sub_score: float | None
    weight: int
    raw: float | None = None
    contrib: float | None = None


@dataclass(frozen=True)
class Score:
    """五因子综合评分结果(§3.3.8.1 / 对齐 scores 表 + §2.21.2 响应)。

    Attributes:
        code: 基金代码。
        composite: 综合分 0-100(缺失因子剔除后)；货基为 None(排除排名)。
        factors: 各因子 {name: {sub_score, weight, raw, contrib}}。
        weights: 使用的权重(可调，ADR-002 仅评估详情调)。
        as_of: 数据截至。
        excluded: 排除原因(如 money)；None 表示参与排名。
    """

    code: str
    composite: float | None
    factors: dict[str, dict[str, Any]] = field(default_factory=dict)
    weights: dict[str, int] = field(default_factory=lambda: dict(SCORE_WEIGHTS))
    as_of: str | None = None
    excluded: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "composite": self.composite,
            "factors": self.factors,
            "weights": self.weights,
            "as_of": self.as_of,
            "excluded": self.excluded,
        }


# ---------------------------------------------------------------------------
# 单因子子分计算(原始指标 -> 0-100)
# ---------------------------------------------------------------------------


def scale_health(aum: float | None) -> float | None:
    """规模健康度子分(非线性，E4)。

    - aum∈[2亿,500亿] -> 100
    - <2亿 -> 触发清盘风险，子分缓降(aum/2亿 * 100)
    - >500亿 -> 钝化，子分缓降(100 - (aum-500)/500 * 20，下限80)
    - None -> None(缺失)

    Args:
        aum: 资产规模(亿元)。
    """
    if aum is None:
        return None
    if aum < SCALE_HEALTHY_MIN:
        # 清盘风险缓降(线性至0)
        return float(aum / SCALE_HEALTHY_MIN * 100.0)
    if aum > SCALE_HEALTHY_MAX:
        # 钝化缓降(下限80)
        return float(max(80.0, 100.0 - (aum - SCALE_HEALTHY_MAX) / SCALE_HEALTHY_MAX * 20.0))
    return 100.0


def manager_excess(fund_return: float | None, benchmark_return: float | None) -> float | None:
    """经理任期超额(=任期收益−同类基准收益，E4)。

    > 标注：任期超额、**非能力归因**(含 β 与幸存者偏差，§3.3.8.1)。
    返回原始超额值(子分归一化由横截面百分位完成)。
    """
    if fund_return is None or benchmark_return is None:
        return None
    return float(fund_return - benchmark_return)


def raw_factor_value(
    name: str, nav: pd.Series | None, aum: float | None, manager_excess_val: float | None
) -> float | None:
    """取因子原始指标值(ret/risk/perf/scale/manager)。

    - ret: 年化收益
    - risk: max_drawdown(负值，E5；越负越差)
    - perf: 业绩持续性(用年化收益的稳定性近似 = 年化收益 / 年化波动；P1-03a 指标)
    - scale: aum(亿元)
    - manager: manager_excess(任期超额)
    """
    if name == "ret":
        if nav is None or len(nav) < 2:
            return None
        return annualized_return(nav)
    if name == "risk":
        if nav is None or len(nav) < 2:
            return None
        return max_drawdown(nav)  # 负值(E5)
    if name == "perf":
        if nav is None or len(nav) < 2:
            return None
        # 业绩持续性：收益/波动(夏普近似)；缺失波动时 None
        from domain.metrics import annualized_volatility

        vol = annualized_volatility(nav)
        if vol is None or vol == 0:
            return None
        return annualized_return(nav) / vol
    if name == "scale":
        return aum
    if name == "manager":
        return manager_excess_val
    return None


# ---------------------------------------------------------------------------
# 横截面百分位归一化(E5，按 asset_class 分组)
# ---------------------------------------------------------------------------


def percentile_subscore(
    values: pd.Series, value: float | None, higher_is_better: bool = True
) -> float | None:
    """单基金某因子值 -> 同类横截面百分位子分(0-100，E5)。

    Args:
        values: 同 asset_class universe 的该因子原始值序列(含本基金)。
        value: 本基金该因子值；None -> 子分 None(缺失剔除)。
        higher_is_better: True=值越大子分越高(ret/perf/scale/manager)；
            False=值越小子分越高(risk=max_drawdown 负值，越负越差 -> 子分越低)。
    Returns:
        0-100 子分；value 缺失或 universe 不足返回 None。
    """
    if value is None:
        return None
    valid = values.dropna()
    if len(valid) < 2:
        return None  # universe 不足无法百分位
    # 百分位：本基金值在 universe 中的排名占比 * 100
    # 注：risk(max_drawdown 负值，E5)值越大(越接近0)子分越高 -> 与正向因子一致
    rank = (valid <= value).sum()
    _ = higher_is_better  # 保留参数语义(当前口径下正向因子与 risk 同向)
    return float(rank / len(valid) * 100.0)


# ---------------------------------------------------------------------------
# 综合分合成
# ---------------------------------------------------------------------------


def compute_composite(factors: dict[str, FactorScore]) -> float | None:
    """综合分合成(§3.3.8.1)：``composite = Σ(w_k·s_k) / Σ w_k``。

    仅对有效(非 None)因子求和；分母随之缩小。全部缺失返回 None。
    """
    num = 0.0
    den = 0
    for fs in factors.values():
        if fs.sub_score is not None:
            contrib = fs.weight * fs.sub_score
            num += contrib
            den += fs.weight
    if den == 0:
        return None
    return num / den


def multi_factor_score(
    code: str,
    *,
    nav: pd.Series | None = None,
    aum: float | None = None,
    manager_excess_val: float | None = None,
    asset_class: str = "equity",
    universe: dict[str, pd.Series] | None = None,
    weights: dict[str, int] | None = None,
    as_of: str | None = None,
) -> Score:
    """五因子综合评分(§3.3.8.1 / DC-003 / ADR-002 唯一权威源)。

    Args:
        code: 基金代码。
        nav: 基金净值序列(ret/risk/perf 用)。
        aum: 资产规模(亿元，scale 用)。
        manager_excess_val: 经理任期超额(manager 用)。
        asset_class: 底层资产类别(equity/debt/money/alt/qdii，E5 分组维度)。
        universe: 横截面 universe，{factor: 同类原始值 Series}；None 则子分无法百分位。
        weights: 可调权重(默认 SCORE_WEIGHTS；ADR-002 仅评估详情调)。
        as_of: 数据截至。
    Returns:
        Score；货基(money)composite=None 且 excluded="money"(E5)。
    """
    w = dict(weights or SCORE_WEIGHTS)

    # 货基排除综合分排名(E5)
    if asset_class == MONEY_EXCLUDED:
        logger.info("score.money_excluded", extra={"action": "score", "code": code})
        return Score(code=code, composite=None, weights=w, as_of=as_of, excluded="money")

    universe = universe or {}

    # 各因子原始值 + 子分
    factors: dict[str, FactorScore] = {}
    higher_is_better = {"ret": True, "risk": True, "perf": True, "scale": True, "manager": True}
    # risk=max_drawdown 负值：值越大(越接近0)子分越高 -> higher_is_better=True
    for name in FACTOR_ORDER:
        raw = raw_factor_value(name, nav, aum, manager_excess_val)
        # scale 子分用 scale_health(非线性，E4)，不参与横截面百分位
        if name == "scale":
            sub = scale_health(raw)
        else:
            uni = universe.get(name)
            sub = percentile_subscore(uni, raw, higher_is_better[name]) if uni is not None else None
            if sub is None and raw is not None:
                # 无 universe 时回退：单基金无法百分位，子分 None(需批算提供 universe)
                pass
        contrib = (w.get(name, 0) * sub) if sub is not None else None
        factors[name] = FactorScore(
            name=name, sub_score=sub, weight=w.get(name, 0), raw=raw, contrib=contrib
        )

    composite = compute_composite(factors)

    return Score(
        code=code,
        composite=composite,
        factors={
            n: {"sub_score": f.sub_score, "weight": f.weight, "raw": f.raw, "contrib": f.contrib}
            for n, f in factors.items()
        },
        weights=w,
        as_of=as_of,
    )


def factor_decomposition(score: Score) -> dict[str, float | None]:
    """因子贡献分解(§3.3.8.1 / DC-003)。返回 {factor: contrib}。"""
    return {name: f["contrib"] for name, f in score.factors.items()}


def recompute_with_weights(score: Score, new_weights: dict[str, int]) -> float | None:
    """滑杆调权后即时重算综合分(ADR-002，仅评估详情)。

    沿用原 sub_score(百分位分位表不变)，仅换权重重算 composite。
    """
    factors: dict[str, FactorScore] = {}
    for name, f in score.factors.items():
        w = new_weights.get(name, 0)
        contrib = (w * f["sub_score"]) if f["sub_score"] is not None else None
        factors[name] = FactorScore(
            name=name, sub_score=f["sub_score"], weight=w, raw=f["raw"], contrib=contrib
        )
    return compute_composite(factors)


__all__: list[str] = [
    "SCORE_WEIGHTS",
    "FACTOR_ORDER",
    "FactorScore",
    "Score",
    "scale_health",
    "manager_excess",
    "raw_factor_value",
    "percentile_subscore",
    "compute_composite",
    "multi_factor_score",
    "factor_decomposition",
    "recompute_with_weights",
]
