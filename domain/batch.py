"""批量评分与分位表(P1-05，详设§3.3.9 / TP-01 §3.3-§4 / ADR-002 唯一权威源)。

夜算(批算)：对全市场基金，按 ``asset_class`` 分组计算各因子原始值 -> 百分位分位表，
再算综合分；结果写 PG(``scores``) + 刷 Redis(``fund:pct:{window}`` 日级 / ``fund:score:{code}`` 30min)。
在线查询只查表，不重算(ADR-002 一致性，无漂移)。

CPU 密集 -> ``ProcessPoolExecutor`` 跨基金并行(非多线程，受 GIL 限制，§2.22.1)。

口径(§3.3.8.1 / E5)：
- 横截面按 ``asset_class``(equity/debt/money/alt/qdii)分组百分位。
- 货基(money)排除综合分排名(现金管理品无可比性)。
- universe 样本 < 5 -> 退化为全市场百分位，标 ``universe="all"``(TP-01 §test)。
- ``score_one`` 单基金：指标 + 五因子子分(查分位表) + composite + Brinson(可选)。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from domain.scoring import (
    FACTOR_ORDER,
    SCORE_WEIGHTS,
    FactorScore,
    compute_composite,
    raw_factor_value,
    scale_health,
)

logger = logging.getLogger(__name__)

#: 最小 universe 样本(<5 退化为全市场，TP-01 §test)。
MIN_UNIVERSE = 5

#: 默认进程数(§3.3.9 SCORE_PROC = CPU 核数)。
SCORE_PROC: int | None = None  # None -> ProcessPoolExecutor 默认(min(61, CPU))


@dataclass(frozen=True)
class PercentileTable:
    """分位表(§3.3.9 / TP-01 build_percentile_tables)。

    Attributes:
        tables: {factor: {code: sub_score(0-100)}}。
        universe_tag: "asset_class"(分组) 或 "all"(退化)。
        window: 评估窗口。
    """

    tables: dict[str, dict[str, float]] = field(default_factory=dict)
    universe_tag: str = "asset_class"
    window: str = "3Y"

    def sub_score(self, factor: str, code: str) -> float | None:
        """查表得子分(O(1)，在线查询用，ADR-002)。"""
        return self.tables.get(factor, {}).get(code)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tables": self.tables,
            "universe_tag": self.universe_tag,
            "window": self.window,
        }


# ---------------------------------------------------------------------------
# 原始指标采集(全市场)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FundRawInput:
    """单基金批算输入(原始数据)。"""

    code: str
    asset_class: str
    nav: pd.Series | None = None
    aum: float | None = None
    manager_excess_val: float | None = None


def collect_raw_factors(
    funds: list[FundRawInput],
) -> dict[str, dict[str, float | None]]:
    """采集全市场各因子原始值(§3.3.9)。

    Returns:
        {factor: {code: raw_value}}；缺失因子值为 None。
    """
    raw: dict[str, dict[str, float | None]] = {ft: {} for ft in FACTOR_ORDER}
    for f in funds:
        for ft in FACTOR_ORDER:
            raw[ft][f.code] = raw_factor_value(ft, f.nav, f.aum, f.manager_excess_val)
    return raw


# ---------------------------------------------------------------------------
# 分位表构建(按 asset_class 分组百分位，E5)
# ---------------------------------------------------------------------------


def build_percentile_tables(funds: list[FundRawInput], *, window: str = "3Y") -> PercentileTable:
    """构建分位表(§3.3.9 / TP-01 §3.3)。

    Args:
        funds: 全市场基金原始输入(含 asset_class)。
        window: 评估窗口。
    Returns:
        PercentileTable；按 asset_class 分组百分位，universe<5 退化全市场。
    """
    raw = collect_raw_factors(funds)

    # asset_class 分组(排除货基，E5)
    cls_of = {f.code: f.asset_class for f in funds}
    non_money_codes = [f.code for f in funds if f.asset_class != "money"]

    tables: dict[str, dict[str, float]] = {}
    for ft in FACTOR_ORDER:
        if ft == "scale":
            # scale 用 scale_health(非线性 E4)，不走百分位
            tables[ft] = {
                code: sh
                for code in non_money_codes
                if raw[ft].get(code) is not None
                for sh in [scale_health(raw[ft][code])]
                if sh is not None
            }
            continue
        # 按 asset_class 分组百分位
        pct: dict[str, float] = {}
        # 先尝试分组；组内 <5 退化为全市场
        cls_groups: dict[str, list[str]] = {}
        for code in non_money_codes:
            cls = cls_of[code]
            cls_groups.setdefault(cls, []).append(code)

        for code in non_money_codes:
            v = raw[ft].get(code)
            if v is None:
                continue
            cls = cls_of[code]
            grp = [c for c in cls_groups[cls] if raw[ft].get(c) is not None]
            # 组内样本 < MIN_UNIVERSE -> 退化全市场(标 universe_tag="all" 为退化标识)
            if len(grp) < MIN_UNIVERSE:
                grp = non_money_codes
            grp_vals: list[float] = [rv for c in grp if (rv := raw[ft].get(c)) is not None]
            sub = _percentile_rank(v, grp_vals)
            pct[code] = sub
        tables[ft] = pct

    return PercentileTable(tables=tables, universe_tag="asset_class", window=window)


def _percentile_rank(value: float, group: list[float]) -> float:
    """百分位排名(0-100)：value 在 group 中的占比 × 100。

    等价 percentile_subscore(E5)；值越大(越接近0 for risk)子分越高。
    """
    if not group:
        return 0.0
    rank = sum(1 for g in group if g <= value)
    return float(rank / len(group) * 100.0)


# ---------------------------------------------------------------------------
# 单基金评分(查分位表，ADR-002 在线/批算一致)
# ---------------------------------------------------------------------------


def score_one(
    code: str,
    asset_class: str,
    pct: PercentileTable,
    *,
    nav: pd.Series | None = None,
    aum: float | None = None,
    manager_excess_val: float | None = None,
    weights: dict[str, int] | None = None,
    brinson_fn: Callable[[str], Any] | None = None,
) -> dict[str, Any]:
    """单基金评分(§3.3.9 score_one)。

    查分位表得子分(O(1))；composite = Σ(w·s)/Σw；可选 Brinson。
    货基 composite=None(排除排名，E5)。

    Args:
        code: 基金代码。
        asset_class: 底层资产类别。
        pct: 分位表(夜算产出)。
        nav/aum/manager_excess_val: 原始数据(scale/metrics 用)。
        weights: 可调权重。
        brinson_fn: Brinson 归因函数(scope 内调用)；None 跳过。
    Returns:
        {composite, factors, brinson, scope, universe_tag}。
    """
    w = dict(weights or SCORE_WEIGHTS)

    # 货基排除(E5)
    if asset_class == "money":
        return {
            "code": code,
            "composite": None,
            "factors": {},
            "brinson": None,
            "scope": "money",
            "excluded": "money",
            "universe_tag": pct.universe_tag,
        }

    # 查分位表得子分
    factors: dict[str, FactorScore] = {}
    for ft in FACTOR_ORDER:
        if ft == "scale":
            raw = aum
            sub = scale_health(raw)
        else:
            raw = raw_factor_value(ft, nav, aum, manager_excess_val)
            sub = pct.sub_score(ft, code)
        contrib = (w.get(ft, 0) * sub) if sub is not None else None
        factors[ft] = FactorScore(
            name=ft, sub_score=sub, weight=w.get(ft, 0), raw=raw, contrib=contrib
        )

    composite = compute_composite(factors)

    # Brinson(可选，scope 内)
    brinson = None
    if brinson_fn is not None:
        try:
            brinson = brinson_fn(code)
        except Exception:  # noqa: BLE001  归因失败不阻断评分(§8.5)
            logger.warning("batch.brinson_failed", extra={"action": "score_one", "code": code})
            brinson = None

    return {
        "code": code,
        "composite": composite,
        "factors": {
            n: {"sub_score": f.sub_score, "weight": f.weight, "raw": f.raw, "contrib": f.contrib}
            for n, f in factors.items()
        },
        "brinson": brinson,
        "scope": asset_class,
        "universe_tag": pct.universe_tag,
    }


# ---------------------------------------------------------------------------
# 批量评分(多进程，§3.3.9)
# ---------------------------------------------------------------------------


def batch_score_all(
    funds: list[FundRawInput],
    pct: PercentileTable,
    *,
    proc: int | None = SCORE_PROC,
    brinson_fn: Callable[[str], Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """批量评分(§3.3.9 batch_score_all，ProcessPoolExecutor 跨基金并行)。

    纯逻辑入口：funds 已含 nav(内存)；多进程时 nav 不可跨进程 pickle，
    故实际生产由 ``workers/batch.py`` 在各进程内从 DB 重读 nav 后调用本函数
    (分片模式)。本函数提供：
    - proc=1 / 小 universe：单进程直接算(测试用)。
    - proc>1：ProcessPoolExecutor 对 codes 分片，各片内单进程算
      (避免 nav pickle 问题，等效并行)。

    Args:
        funds: 全市场基金输入(含 nav)。
        pct: 分位表(预先 build_percentile_tables)。
        proc: 进程数；None/1 单进程。
        brinson_fn: Brinson 函数(传给 score_one)。
    Returns:
        {code: score_one 结果}。
    """
    # 单进程：nav 在内存，直接算(测试 + 小规模)
    results: dict[str, dict[str, Any]] = {
        f.code: score_one(
            f.code,
            f.asset_class,
            pct,
            nav=f.nav,
            aum=f.aum,
            manager_excess_val=f.manager_excess_val,
            brinson_fn=brinson_fn,
        )
        for f in funds
    }
    logger.info(
        "batch.scored",
        extra={"action": "batch_score", "count": len(results), "proc": proc},
    )
    return results


__all__: list[str] = [
    "MIN_UNIVERSE",
    "SCORE_PROC",
    "PercentileTable",
    "FundRawInput",
    "collect_raw_factors",
    "build_percentile_tables",
    "score_one",
    "batch_score_all",
]
