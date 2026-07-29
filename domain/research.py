"""PEG/ERP 基金层代理 + 守卫(P1-03d，详设§3.3.7 / TP-01 §3.4 / DC-003 / §4 红线 E7/E10)。

背景(消除难点 A)：PEG=PE/盈利增速、ERP=股票预期收益−无风险利率，本是"股票/指数级"指标；
基金无直接"盈利"，naive 套用会误导 -> 全部改为"代理值(proxy)"并显式标注。

守卫(``RESEARCH_PROXY_GUARD``，§3.3.7)：口径未定义前 ``peg/erp`` 一律 None，禁止 naive 计算；
未定义口径经守卫拦截 -> 40301(§4.2)。

PEG 代理(闭合 E7)：
- ``PEG_i = PE_i / growth_i``(%)，按持仓权重加权(主动基)/ 跟踪基准加权(指数ETF)
- **剔除 PE≤0(亏损)与 growth 越界/缺失个股(不置 0)**
- 债基返 None；持仓缺失回退跟踪基准，不可得 ``available=False``

ERP 代理(闭合 E10)：
- ``EY = 组合加权盈利收益率``；``ERP = EY − 10Y 国债``
- **拆大/小盘加权(7:3)**，避免单一宽基口径误导
- 债基返 None

展示约束(硬性)：卡片 name 带"(代理)"，解读含"相对高低提示，非绝对结论"；
``available=False`` 时卡片显示"数据不足/代理值待定"，禁止展示任何数值。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

#: 守卫开关(§3.3.7)。开启后：口径未定义前 peg/erp 一律 None，禁止 naive 计算。
RESEARCH_PROXY_GUARD: bool = True

#: ERP 大/小盘加权比例(E10，TP-05 §3 / 详设 §3.7)。
ERP_LARGE_WEIGHT = 0.7
ERP_SMALL_WEIGHT = 0.3

#: PEG 个股增长越界判定(E7：growth 须 0<g<100)。
PEG_GROWTH_MIN = 0.0
PEG_GROWTH_MAX = 100.0

#: 卡片名称后缀(硬性展示约束)。
PROXY_SUFFIX = "(代理)"
PROXY_NOTE = "相对高低提示，非绝对结论；ERP 为盈利收益率利差代理"
UNAVAILABLE_MSG = "数据不足/代理值待定"

#: 阈值着色(DC-003，技术规格 RESEARCH_THRESHOLDS；peg/erp 为代理值相对高低提示线)。
RESEARCH_THRESHOLDS: dict[str, float] = {
    "alpha": 0.0,
    "beta": 1.0,
    "track_err": 2.0,
    "info_ratio": 0.5,
    "peg": 1.0,
    "erp": 3.0,
}

#: 仅主动股混基做 PEG/ERP 代理(与 BRINSON_SCOPE 一致)。
PEG_SCOPE: list[str] = ["mixed", "stock"]


@dataclass(frozen=True)
class ProxyResult:
    """代理值结果(对齐 ProxyResult，§3.3.7 / TP-01)。

    Attributes:
        value: 代理值(PEG 或 ERP)；None 表示不可得。
        method: 代理方法(holdings_weighted / ey_minus_rf 等)。
        is_proxy: 恒 True(代理值，非真实指标)。
        available: 是否可得；False 时禁止展示数值。
        as_of: 数据截至。
        source: 数据来源。
        name_suffix: 展示后缀"(代理)"。
    """

    value: float | None
    method: str
    is_proxy: bool = True
    available: bool = False
    as_of: str | None = None
    source: str | None = None
    name_suffix: str = PROXY_SUFFIX

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "method": self.method,
            "is_proxy": self.is_proxy,
            "available": self.available,
            "as_of": self.as_of,
            "source": self.source,
            "name_suffix": self.name_suffix,
        }


@dataclass(frozen=True)
class ERPResult:
    """ERP 代理结果(拆大/小盘，E10)。"""

    large: float | None = None
    small: float | None = None
    weighted: float | None = None  # 大/小盘加权(7:3)
    ey_large: float | None = None
    ey_small: float | None = None
    available: bool = False
    method: str = "ey_minus_rf"

    def to_dict(self) -> dict[str, Any]:
        return {
            "large": self.large,
            "small": self.small,
            "weighted": self.weighted,
            "ey_large": self.ey_large,
            "ey_small": self.ey_small,
            "available": self.available,
            "method": self.method,
        }


@dataclass(frozen=True)
class MetricCard:
    """研究指标卡片(§3.3.7 / 技术规格 research_metrics_cards)。"""

    name: str
    value: float | None
    threshold_ok: bool
    interpretation: str
    available: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "threshold_ok": self.threshold_ok,
            "interpretation": self.interpretation,
            "available": self.available,
        }


# ---------------------------------------------------------------------------
# PEG 代理(闭合 E7)
# ---------------------------------------------------------------------------


def peg_proxy(
    fund_type: str,
    holdings: list[dict[str, Any]] | None,
    *,
    benchmark_holdings: list[dict[str, Any]] | None = None,
    as_of: str | None = None,
    guard: bool = RESEARCH_PROXY_GUARD,
) -> ProxyResult:
    """基金层 PEG 代理(§3.3.7 / TP-01 §3.4 / E7)。

    Args:
        fund_type: 基金类型(债基返 None)。
        holdings: 持仓快照 [{"stock", "weight", "pe", "growth"}]。
        benchmark_holdings: 跟踪基准持仓(指数/ETF 或持仓缺失回退用)。
        as_of: 数据截至。
        guard: 守卫开关；True 且口径未定义时一律 None。
    Returns:
        ProxyResult；PEG = Σ(w_i × PE_i/growth_i)，剔除 PE≤0/growth 越界。
    """
    # 守卫：口径未定义前一律 None(§3.3.7，防 naive)
    if guard and not _guard_passed():
        return ProxyResult(value=None, method="guard_blocked", available=False, as_of=as_of)

    # 债基无 PEG 代理(§3.3.7)
    if fund_type not in PEG_SCOPE:
        return ProxyResult(value=None, method="bond_no_peg", available=False, as_of=as_of)

    # 持仓缺失 -> 回退跟踪基准(§3.3.7)
    source = "holdings"
    hp = holdings
    if not hp:
        hp = benchmark_holdings
        source = "benchmark_fallback"
    if not hp:
        # 不可得 -> available=False，绝不硬算(§3.3.7 硬性)
        return ProxyResult(value=None, method="holdings_missing", available=False, as_of=as_of)

    # PEG_i = PE_i / growth_i；剔除 PE≤0(亏损)与 growth 越界/缺失(E7，不置 0)
    pegs: list[float] = []
    weights: list[float] = []
    for h in hp:
        pe = h.get("pe")
        g = h.get("growth")
        if pe is None or pe <= 0:  # E7：剔除 PE≤0
            continue
        if g is None or not (PEG_GROWTH_MIN < g < PEG_GROWTH_MAX):  # E7：growth 越界/缺失
            continue
        pegs.append(pe / g)
        weights.append(float(h.get("weight", 0.0)))

    if not pegs:
        return ProxyResult(
            value=None, method="holdings_weighted", available=False, as_of=as_of, source=source
        )

    peg = _weighted_mean(pegs, weights)
    return ProxyResult(
        value=peg, method="holdings_weighted", available=True, as_of=as_of, source=source
    )


# ---------------------------------------------------------------------------
# ERP 代理(闭合 E10，拆大/小盘 7:3)
# ---------------------------------------------------------------------------


def erp_proxy(
    fund_type: str,
    holdings: list[dict[str, Any]] | None,
    rf_rate: float,
    *,
    benchmark_holdings: list[dict[str, Any]] | None = None,
    as_of: str | None = None,
    guard: bool = RESEARCH_PROXY_GUARD,
) -> ERPResult:
    """基金层 ERP 代理(§3.3.7 / E10 拆大/小盘)。

    Args:
        fund_type: 基金类型(债基返 None)。
        holdings: 持仓 [{"stock","weight","ey","style"}]，style∈{large,small}。
        rf_rate: 10Y 国债收益率(无风险利率)。
        benchmark_holdings: 跟踪基准回退。
        as_of: 数据截至。
        guard: 守卫开关。
    Returns:
        ERPResult(大/小盘 + 加权 7:3)；EY − rf。
    """
    if guard and not _guard_passed():
        return ERPResult(available=False, method="guard_blocked")

    if fund_type not in PEG_SCOPE:
        return ERPResult(available=False, method="bond_no_erp")

    hp = holdings
    if not hp:
        hp = benchmark_holdings
    if not hp:
        return ERPResult(available=False, method="holdings_missing")

    # 按市值风格拆大/小盘(E10)
    ey_large = _ey_weighted(hp, style="large")
    ey_small = _ey_weighted(hp, style="small")

    erp_large = (ey_large - rf_rate) if ey_large is not None else None
    erp_small = (ey_small - rf_rate) if ey_small is not None else None

    # 大/小盘加权(7:3，E10)；缺失时用可得项
    weighted = _erp_weighted(erp_large, erp_small)
    available = weighted is not None

    return ERPResult(
        large=erp_large,
        small=erp_small,
        weighted=weighted,
        ey_large=ey_large,
        ey_small=ey_small,
        available=available,
    )


# ---------------------------------------------------------------------------
# 研究指标卡片(§3.3.7 / 技术规格 research_metrics_cards)
# ---------------------------------------------------------------------------


def research_metrics_cards(
    peg: ProxyResult,
    erp: ERPResult,
    *,
    alpha: float | None = None,
    beta: float | None = None,
    track_err: float | None = None,
    info_ratio_val: float | None = None,
) -> list[MetricCard]:
    """研究指标卡片(§3.3.7 / DC-003)：阈值着色 + 一句话解读。

    peg/erp 为代理值，name 带"(代理)"，解读含"相对高低提示，非绝对结论"；
    available=False 时显示"数据不足/代理值待定"，禁止展示数值(硬性约束)。
    """
    cards: list[MetricCard] = []

    # PEG 卡(代理)
    if peg.available and peg.value is not None:
        ok = peg.value <= RESEARCH_THRESHOLDS["peg"]
        cards.append(
            MetricCard(
                name=f"PEG{PROXY_SUFFIX}",
                value=peg.value,
                threshold_ok=ok,
                interpretation=f"{'偏低' if ok else '偏高'}(代理)；{PROXY_NOTE}",
            )
        )
    else:
        cards.append(
            MetricCard(
                name=f"PEG{PROXY_SUFFIX}",
                value=None,
                threshold_ok=False,
                interpretation=UNAVAILABLE_MSG,
                available=False,
            )
        )

    # ERP 卡(代理)
    erp_val = erp.weighted
    if erp.available and erp_val is not None:
        ok = erp_val >= RESEARCH_THRESHOLDS["erp"]
        cards.append(
            MetricCard(
                name=f"ERP{PROXY_SUFFIX}",
                value=erp_val,
                threshold_ok=ok,
                interpretation=f"{'权益吸引力较高' if ok else '偏低'}(代理,大/小盘7:3)；{PROXY_NOTE}",
            )
        )
    else:
        cards.append(
            MetricCard(
                name=f"ERP{PROXY_SUFFIX}",
                value=None,
                threshold_ok=False,
                interpretation=UNAVAILABLE_MSG,
                available=False,
            )
        )

    # 普通(非代理)指标
    if alpha is not None:
        cards.append(
            MetricCard(
                name="Alpha",
                value=alpha,
                threshold_ok=alpha >= RESEARCH_THRESHOLDS["alpha"],
                interpretation="超额收益为正" if alpha >= 0 else "跑输基准",
            )
        )
    if beta is not None:
        cards.append(
            MetricCard(
                name="Beta",
                value=beta,
                threshold_ok=abs(beta - RESEARCH_THRESHOLDS["beta"]) < 0.5,
                interpretation=f"{'接近1' if abs(beta-1)<0.5 else '偏离基准波动'}",
            )
        )
    if track_err is not None:
        cards.append(
            MetricCard(
                name="跟踪误差",
                value=track_err,
                threshold_ok=track_err <= RESEARCH_THRESHOLDS["track_err"],
                interpretation="跟踪良好" if track_err <= 2 else "偏离较大",
            )
        )
    if info_ratio_val is not None:
        cards.append(
            MetricCard(
                name="信息比率",
                value=info_ratio_val,
                threshold_ok=info_ratio_val >= RESEARCH_THRESHOLDS["info_ratio"],
                interpretation="主动管理有效" if info_ratio_val >= 0.5 else "主动管理不足",
            )
        )

    return cards


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------


def _guard_passed() -> bool:
    """守卫通过判定(§3.3.7)。

    当前口径已定义(PEG/ERP 代理算法在 TP-01 §3.4 落地)，守卫通过。
    口径真正未定义时应返 False(返回 None，40301)。
    """
    return True  # 口径已定义(P1-03d)


def _weighted_mean(values: list[float], weights: list[float]) -> float:
    """加权平均(权重为 0 时回退算术平均)。"""
    total_w = sum(weights)
    if total_w == 0:
        return sum(values) / len(values) if values else 0.0
    return sum(v * w for v, w in zip(values, weights, strict=False)) / total_w


def _ey_weighted(holdings: list[dict[str, Any]], *, style: str) -> float | None:
    """按风格(large/small)加权盈利收益率 EY。

    holdings 项含 ``ey``(盈利收益率)与 ``style``(large/small)；缺失 ey 的项跳过。
    """
    eys: list[float] = []
    weights: list[float] = []
    for h in holdings:
        if h.get("style") != style:
            continue
        ey = h.get("ey")
        if ey is None:
            continue
        eys.append(float(ey))
        weights.append(float(h.get("weight", 0.0)))
    if not eys:
        return None
    return _weighted_mean(eys, weights)


def _erp_weighted(large: float | None, small: float | None) -> float | None:
    """大/小盘 ERP 加权(7:3，E10)；缺失项用可得项(全缺返 None)。"""
    if large is not None and small is not None:
        return large * ERP_LARGE_WEIGHT + small * ERP_SMALL_WEIGHT
    if large is not None:
        return large  # 仅大盘可得
    if small is not None:
        return small  # 仅小盘可得
    return None


__all__: list[str] = [
    "RESEARCH_PROXY_GUARD",
    "ERP_LARGE_WEIGHT",
    "ERP_SMALL_WEIGHT",
    "PEG_GROWTH_MIN",
    "PEG_GROWTH_MAX",
    "PROXY_SUFFIX",
    "PROXY_NOTE",
    "UNAVAILABLE_MSG",
    "RESEARCH_THRESHOLDS",
    "PEG_SCOPE",
    "ProxyResult",
    "ERPResult",
    "MetricCard",
    "peg_proxy",
    "erp_proxy",
    "research_metrics_cards",
]
