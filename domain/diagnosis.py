"""组合多层级诊断(P1-08b，详设§3.6.6.1 / TP-03 / DC-006 / §4 红线 E8/E9/E12)。

五维红黄绿诊断：股债(asset) / 海外(overseas) / 行业(industry) / 风格(style) / 个基(single)。
整体评级合成：任一红->红，否则任一黄->黄，否则绿。

口径红线(§4)：
- E8：股债目标仓位由 ``risk_type`` 推导(保守 20-40% / 稳健 40-60% / 进取 60-80%)。
- E9：止损=相对基准超额<-15% 或 回撤>30% 红；止盈软提示(不硬止盈)。
- E12：费率预警 > 2.0%(含托管综合费率)。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from domain.stylebox import VG_GROWTH

logger = logging.getLogger(__name__)

#: 状态枚举。
RED, YELLOW, GREEN = "red", "yellow", "green"

#: 股债维目标仓位(E8，由 risk_type 推导)。
ASSET_TARGET: dict[str, tuple[float, float]] = {
    "conservative": (0.2, 0.4),  # 保守 20-40%
    "moderate": (0.4, 0.6),  # 稳健 40-60%
    "aggressive": (0.6, 0.8),  # 进取 60-80%
}

#: 再平衡偏离阈值(§5)。
REBALANCE_DRIFT = 0.05

#: 诊断阈值(TP-03 §3，集中配置便于审定)。
THRESHOLDS = {
    "overseas_region_max": 0.25,  # 单一海外区域占比
    "overseas_total_max": 0.40,  # 海外合计
    "industry_single_max": 0.60,  # 单一行业占比
    "industry_hhi_red": 0.25,  # HHI 红线
    "industry_hhi_yellow": 0.15,  # HHI 黄线
    "style_growth_max": 0.70,  # 成长风格暴露
    "single_excess_loss": -0.15,  # 相对基准超额(E9)
    "single_max_drawdown": 0.30,  # 最大回撤(E9)
    "single_profit_soft": 0.30,  # 止盈软提示(E9)
    "single_scale_bloat": 500.0,  # 规模臃肿(亿)
    "single_fee_max": 0.02,  # 综合费率(E12, 2.0%)
    "single_turnover_max": 3.0,  # 换手率
}

#: 权益类类型(股债维判定用)。
EQUITY_TYPES = {"stock", "mixed", "index", "etf"}
#: 海外类型。
OVERSEAS_TYPES = {"qdii"}


@dataclass(frozen=True)
class DimResult:
    """单维诊断结果。"""

    dim: str
    status: str  # red/yellow/green
    detail: str
    advice: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dim": self.dim,
            "status": self.status,
            "detail": self.detail,
            "advice": self.advice,
            "metrics": self.metrics,
        }


@dataclass(frozen=True)
class DiagnosisReport:
    """组合诊断报告(TP-03 §4)。"""

    portfolio_id: str
    per_dim: dict[str, dict[str, Any]] = field(default_factory=dict)
    rating: str = GREEN
    advice: list[str] = field(default_factory=list)
    rebalance: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "portfolio_id": self.portfolio_id,
            "per_dim": self.per_dim,
            "rating": self.rating,
            "advice": self.advice,
            "rebalance": self.rebalance,
        }


def diagnose(
    portfolio_id: str,
    weights: dict[str, float],
    *,
    fund_types: dict[str, str] | None = None,
    risk_type: str = "moderate",
    fund_metrics: dict[str, dict[str, Any]] | None = None,
    fund_styles: dict[str, tuple[str | None, str | None]] | None = None,
) -> DiagnosisReport:
    """组合诊断(§3.6.6.1 / TP-03 §4)。

    Args:
        portfolio_id: 组合 ID。
        weights: {code: weight}。
        fund_types: {code: fund_type}；None 时按权重推断。
        risk_type: 风险偏好(conservative/moderate/aggressive，E8)。
        fund_metrics: {code: {excess, max_drawdown, scale, fee_rate, turnover}}；
            None 时个基维跳过。
        fund_styles: {code: (size, value_growth)}(风格箱，§3.4 风格维)；
            None/缺项时风格维回退权益占比近似。
    Returns:
        DiagnosisReport。
    """
    fund_types = fund_types or {}
    fund_metrics = fund_metrics or {}
    fund_styles = fund_styles or {}

    # 五维诊断
    asset = _asset_dim(weights, fund_types, risk_type)
    overseas = _overseas_dim(weights, fund_types)
    industry = _industry_dim(weights)  # MVP：无行业数据 -> green(待 P3 穿透)
    style = _style_dim(weights, fund_types, risk_type, fund_styles)
    single = _single_fund_dim(weights, fund_metrics)

    per_dim = {
        "asset": asset.to_dict(),
        "overseas": overseas.to_dict(),
        "industry": industry.to_dict(),
        "style": style.to_dict(),
        "single": single.to_dict(),
    }

    # 整体评级(TP-03 §4)
    states = [d.status for d in [asset, overseas, industry, style, single]]
    rating = _overall(states)

    # 建议汇总
    advice = [d.advice for d in [asset, overseas, industry, style, single] if d.advice]

    # 再平衡提醒(§5)
    rebalance = _rebalance(per_dim, weights, risk_type, fund_types)

    return DiagnosisReport(
        portfolio_id=portfolio_id,
        per_dim=per_dim,
        rating=rating,
        advice=advice,
        rebalance=rebalance,
    )


def _overall(states: list[str]) -> str:
    """整体评级合成(TP-03 §4)。"""
    if any(s == RED for s in states):
        return RED
    if any(s == YELLOW for s in states):
        return YELLOW
    return GREEN


# ---------------------------------------------------------------------------
# 各维诊断
# ---------------------------------------------------------------------------


def _asset_dim(weights: dict[str, float], fund_types: dict[str, str], risk_type: str) -> DimResult:
    """股债维(E8：目标仓位由 risk_type 推导)。"""
    target = ASSET_TARGET.get(risk_type, ASSET_TARGET["moderate"])
    equity = sum(w for c, w in weights.items() if fund_types.get(c, "mixed") in EQUITY_TYPES)
    lo, hi = target
    if equity < lo or equity > hi:
        return DimResult(
            "asset",
            RED,
            f"权益仓位 {equity*100:.1f}%，目标区间 {lo*100:.0f}-{hi*100:.0f}%(risk_type={risk_type})",
            f"调整权益仓位至 {lo*100:.0f}-{hi*100:.0f}%",
            {"equity_ratio": equity, "target": list(target)},
        )
    return DimResult(
        "asset",
        GREEN,
        f"权益仓位 {equity*100:.1f}% 适中",
        metrics={"equity_ratio": equity, "target": list(target)},
    )


def _overseas_dim(weights: dict[str, float], fund_types: dict[str, str]) -> DimResult:
    """海外维(§3.2)。"""
    overseas = sum(w for c, w in weights.items() if fund_types.get(c) in OVERSEAS_TYPES)
    if overseas > THRESHOLDS["overseas_total_max"]:
        return DimResult(
            "overseas",
            YELLOW,
            f"海外合计 {overseas*100:.1f}% 偏高(>40%)",
            "注意汇率/时区风险",
            {"overseas_total": overseas},
        )
    return DimResult(
        "overseas",
        GREEN,
        f"海外配置 {overseas*100:.1f}% 适度",
        metrics={"overseas_total": overseas},
    )


def _industry_dim(weights: dict[str, float]) -> DimResult:
    """行业维(§3.3，MVP：无行业数据 -> 待 P3 穿透)。"""
    # TODO(P3-01a 穿透)：按持仓穿透行业聚合算 HHI
    return DimResult("industry", GREEN, "行业集中度待穿透数据(P3)", metrics={"available": False})


def _style_dim(
    weights: dict[str, float],
    fund_types: dict[str, str],
    risk_type: str,
    fund_styles: dict[str, tuple[str | None, str | None]] | None = None,
) -> DimResult:
    """风格维(§3.4 / TP-03 §3)：风格箱成长暴露判定，缺风格箱回退权益占比近似。

    有风格箱 -> 成长暴露 = Σ(权重 where value_growth=成长)；
    无风格箱 -> 权益类占比 × 0.5 近似(MVP 占位，标 available=False)。
    保守偏好下成长暴露超阈值 -> 红(E8 风格错配)。
    """
    if fund_styles:
        growth_exposure = sum(
            w for c, w in weights.items() if (fund_styles.get(c) or (None, None))[1] == VG_GROWTH
        )
        if growth_exposure > THRESHOLDS["style_growth_max"] and risk_type == "conservative":
            return DimResult(
                "style",
                RED,
                f"成长暴露 {growth_exposure*100:.0f}% 与保守偏好错配",
                "降低成长风格暴露",
                metrics={
                    "growth_exposure": growth_exposure,
                    "available": True,
                    "source": "stylebox",
                },
            )
        return DimResult(
            "style",
            GREEN,
            f"成长暴露 {growth_exposure*100:.0f}%(风格箱口径)",
            metrics={
                "growth_exposure": growth_exposure,
                "available": True,
                "source": "stylebox",
            },
        )

    # 回退：权益占比近似(MVP 占位)
    growth_exposure = (
        sum(w for c, w in weights.items() if fund_types.get(c) in EQUITY_TYPES) * 0.5
    )  # 简化近似
    if growth_exposure > THRESHOLDS["style_growth_max"] and risk_type == "conservative":
        return DimResult(
            "style",
            RED,
            f"成长暴露 {growth_exposure*100:.0f}% 与保守偏好错配(权益占比近似)",
            "降低成长风格暴露",
            metrics={
                "growth_exposure": growth_exposure,
                "available": False,
                "source": "equity_proxy",
            },
        )
    return DimResult(
        "style",
        GREEN,
        "风格配置待风格箱数据(权益占比近似)",
        metrics={
            "growth_exposure": growth_exposure,
            "available": False,
            "source": "equity_proxy",
        },
    )


def _single_fund_dim(
    weights: dict[str, float], fund_metrics: dict[str, dict[str, Any]]
) -> DimResult:
    """个基维(E9/E12，逐成分检查)。"""
    if not fund_metrics:
        return DimResult("single", GREEN, "个基隐患待指标数据", metrics={"available": False})
    red_count = 0
    yellow_count = 0
    for code, _w in weights.items():
        m = fund_metrics.get(code, {})
        # E9：止损红线(相对基准超额<-15% 或 回撤>30%)
        excess = m.get("excess")
        max_dd = m.get("max_drawdown")
        if (excess is not None and excess < THRESHOLDS["single_excess_loss"]) or (
            max_dd is not None and max_dd > THRESHOLDS["single_max_drawdown"]
        ):
            red_count += 1
            continue
        # E9：止盈软提示
        ret = m.get("return")
        if ret is not None and ret > THRESHOLDS["single_profit_soft"]:
            yellow_count += 1
        # E12：费率
        fee = m.get("fee_rate")
        if fee is not None and fee > THRESHOLDS["single_fee_max"]:
            yellow_count += 1
        # 规模臃肿
        scale = m.get("scale")
        if scale is not None and scale > THRESHOLDS["single_scale_bloat"]:
            yellow_count += 1

    if red_count > 0:
        return DimResult(
            "single",
            RED,
            f"{red_count} 个成分触发止损红线(E9)",
            "评估止损/减仓",
            {"red_count": red_count, "yellow_count": yellow_count},
        )
    if yellow_count > 0:
        return DimResult(
            "single",
            YELLOW,
            f"{yellow_count} 个成分有隐患提示",
            "关注止盈/费率/规模",
            {"red_count": red_count, "yellow_count": yellow_count},
        )
    return DimResult("single", GREEN, "个基无隐患", metrics={"red_count": 0, "yellow_count": 0})


def _rebalance(
    per_dim: dict[str, dict[str, Any]],
    weights: dict[str, float],
    risk_type: str,
    fund_types: dict[str, str],
) -> list[dict[str, Any]]:
    """再平衡提醒(§5：偏离目标 > 5% 触发)。"""
    rebal: list[dict[str, Any]] = []
    # 股债维偏离
    target = ASSET_TARGET.get(risk_type, ASSET_TARGET["moderate"])
    equity = sum(w for c, w in weights.items() if fund_types.get(c, "mixed") in EQUITY_TYPES)
    lo, hi = target
    mid = (lo + hi) / 2
    if abs(equity - mid) > REBALANCE_DRIFT:
        rebal.append(
            {
                "dim": "asset",
                "current": round(equity, 4),
                "target": round(mid, 4),
                "action": f"权益 {equity*100:.1f}% -> {mid*100:.1f}%",
            }
        )
    return rebal


__all__: list[str] = [
    "RED",
    "YELLOW",
    "GREEN",
    "ASSET_TARGET",
    "REBALANCE_DRIFT",
    "THRESHOLDS",
    "DimResult",
    "DiagnosisReport",
    "diagnose",
]
