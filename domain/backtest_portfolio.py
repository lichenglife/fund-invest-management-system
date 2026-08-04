"""组合回测(P1-08c，详设§3.6.2/§3.6.7 / TP-04 §4 / CLAUDE.md §4 E3/E14 红线)。

给定权重组合 vs 自适应基准(全收益指数)的历史回放：累计收益/回撤/夏普/超额。

E3 红线：统一**后复权净值(adj_nav)**，删 DIVIDEND_MODE(后复权已含分红再投)。
E14 红线：基准默认**全收益指数**，按组合底层 asset_class 自动选(权益->沪深300全收益 /
           债券->中债综合财富 / QDII->标普500全收益)，用户可覆盖。
防未来函数：日收益用 ``pct_change``(t-1->t)，组合与基准均后复权/全收益口径，分红处理一致。

口径(TP-04 §4)：
- 组合日收益 = Σ weight_i × 个基日收益(后复权净值收益)。
- 区间内某成分净值缺失 -> 该段收益置 0(持有现金)，标 ``partial=True``。
- 回测起点 = max(各成分最早净值日, start)；样本<60 日标 ``low_sample``。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

#: 年化因子(A股约 244 交易日)。
TRADING_DAYS = 244

#: 全收益指数代码表(E14，含分红再投资)；用户可在请求中覆盖 bench。
TOTAL_RETURN_BENCH: dict[str, str] = {
    "equity": "H00300.SH",  # 沪深300全收益(权益型组合默认)
    "mixed": "H00300.SH",  # 偏股混合型同权益
    "bond": "CBA02701.CS",  # 中债-综合财富(总值)指数(债券型组合默认)
    "money": "CBA00101.CS",  # 中债-总财富(1-3年)或货基可比基准
    "alt": "H00300.SH",  # 另类(FOF 等)缺专用基准时回退沪深300全收益
    "qdii": "SPXT.INX",  # QDII 用标普500全收益(示例)
}

#: 基金类型 -> 资产类别(基准选择用)。
TYPE_TO_ASSET_CLASS: dict[str, str] = {
    "stock": "equity",
    "index": "equity",
    "etf": "equity",
    "mixed": "mixed",
    "bond": "bond",
    "money": "money",
    "qdii": "qdii",
}

#: 样本不足阈值(交易日)。
LOW_SAMPLE_DAYS = 60

#: 权重和超阈值拒绝(§5 边界)。
WEIGHT_SUM_REJECT = 1.05


@dataclass(frozen=True)
class PortfolioBacktestResult:
    """组合回测结果(TP-04 §4)。"""

    cum_return: float = 0.0  # 组合累计收益
    max_drawdown: float = 0.0  # 最大回撤(负值，E5)
    sharpe: float | None = None  # 年化夏普
    bench: str = ""
    bench_cum_return: float | None = None  # 基准累计收益
    excess_cum: float | None = None  # 累计超额
    excess_ann: float | None = None  # 年化超额
    partial: bool = False  # 某成分区间缺失
    low_sample: bool = False  # 样本不足
    nav_curve: list[dict[str, Any]] = field(default_factory=list)  # 组合净值曲线

    def to_dict(self) -> dict[str, Any]:
        return {
            "cum_return": self.cum_return,
            "max_drawdown": self.max_drawdown,
            "sharpe": self.sharpe,
            "bench": self.bench,
            "bench_cum_return": self.bench_cum_return,
            "excess_cum": self.excess_cum,
            "excess_ann": self.excess_ann,
            "partial": self.partial,
            "low_sample": self.low_sample,
            "nav_curve": self.nav_curve,
        }


def pick_benchmark(
    weights: dict[str, float], fund_types: dict[str, str] | None = None
) -> str:
    """按组合底层资产类别加权主导项选基准(E14)。

    Args:
        weights: {code: weight}。
        fund_types: {code: fund_type}；None 时按 mixed 推断。
    Returns:
        全收益指数代码。
    """
    fund_types = fund_types or {}
    ac_weights: dict[str, float] = {}
    for code, w in weights.items():
        ft = fund_types.get(code, "mixed")
        ac = TYPE_TO_ASSET_CLASS.get(ft, "mixed")
        ac_weights[ac] = ac_weights.get(ac, 0.0) + w
    if not ac_weights:
        return TOTAL_RETURN_BENCH["equity"]
    dom = max(ac_weights, key=lambda k: ac_weights[k])
    return TOTAL_RETURN_BENCH.get(dom, TOTAL_RETURN_BENCH["equity"])


def portfolio_backtest(
    nav_dict: dict[str, pd.Series],
    weights: dict[str, float],
    *,
    bench_nav: pd.Series | None = None,
    bench_code: str = "",
) -> PortfolioBacktestResult:
    """组合回测(TP-04 §4)。

    Args:
        nav_dict: {code: 后复权净值序列(adj_nav，E3；index=日期)}。
        weights: {code: weight}；无需归一化(内部归一)。
        bench_nav: 基准全收益净值序列；None 时仅返回组合指标(bench 标 unavailable)。
        bench_code: 基准代码(用户覆盖或 pick_benchmark 结果)。
    Returns:
        PortfolioBacktestResult。
    """
    # 仅保留有权重且有净值的成分
    codes = [c for c in weights if c in nav_dict and nav_dict[c] is not None and len(nav_dict[c]) > 1]
    if not codes:
        return PortfolioBacktestResult()

    # 权重归一化(§5：和≠1 归一化并提示；>1.05 由 API 层拒绝)
    raw_w = {c: weights[c] for c in codes}
    total_w = sum(raw_w.values())
    if total_w <= 0:
        return PortfolioBacktestResult()
    norm_w = {c: w / total_w for c, w in raw_w.items()}

    partial = len(codes) < len(weights)

    # 各成分日收益(pct_change = t-1->t，无未来函数)；对齐到公共交易日
    rets = pd.DataFrame({c: nav_dict[c].pct_change() for c in codes}).dropna(how="all")
    # 缺失段置 0(持有现金，§5)；NAV=0 产生 inf 也置 0(§4 红线不崩溃)
    rets = rets.replace([np.inf, -np.inf], 0.0).fillna(0.0)

    # 组合日收益 = Σ w_i × ret_i(严格时序，无未来函数)
    w_series = pd.Series({c: norm_w[c] for c in rets.columns})
    port_ret = (rets * w_series).sum(axis=1)

    if len(port_ret) < 2:
        return PortfolioBacktestResult(partial=partial, low_sample=True)

    cum_return = float((1.0 + port_ret).prod() - 1.0)
    max_dd = _max_drawdown(port_ret)
    sharpe = _sharpe(port_ret)
    low_sample = len(port_ret) < LOW_SAMPLE_DAYS

    # 净值曲线(累计净值，起点=1)
    cum_nav = (1.0 + port_ret).cumprod()
    # 采样输出(最多 200 点，避免前端渲染压力)
    step = max(1, len(cum_nav) // 200)
    nav_curve = [
        {"date": d.isoformat(), "nav": round(float(v), 6)}
        for d, v in zip(cum_nav.index[::step], cum_nav.values[::step], strict=False)
    ]

    # 基准对比(E14)
    bench_cum: float | None = None
    excess_cum: float | None = None
    excess_ann: float | None = None
    if bench_nav is not None and len(bench_nav) > 1:
        bench_ret = bench_nav.pct_change().dropna()
        # 对齐到组合交易日
        aligned = pd.DataFrame({"port": port_ret, "bench": bench_ret}).dropna()
        if len(aligned) > 1:
            bench_cum = float((1.0 + aligned["bench"]).prod() - 1.0)
            excess_cum = float((1.0 + aligned["port"]).prod() - (1.0 + aligned["bench"]).prod())
            excess_ann = _annualized_excess(aligned["port"], aligned["bench"])

    return PortfolioBacktestResult(
        cum_return=cum_return,
        max_drawdown=max_dd,
        sharpe=sharpe,
        bench=bench_code,
        bench_cum_return=bench_cum,
        excess_cum=excess_cum,
        excess_ann=excess_ann,
        partial=partial,
        low_sample=low_sample,
        nav_curve=nav_curve,
    )


def _max_drawdown(returns: pd.Series) -> float:
    """最大回撤(负值，E5)。"""
    if len(returns) < 2:
        return 0.0
    cum = (1.0 + returns).cumprod()
    peak = cum.cummax()
    dd = (cum - peak) / peak
    return float(dd.min()) if len(dd) > 0 else 0.0


def _sharpe(returns: pd.Series) -> float | None:
    """年化夏普(无风险利率=0，年化因子 TRADING_DAYS)。"""
    if len(returns) < 2:
        return None
    std = float(returns.std(ddof=1))
    if std == 0:
        return None
    mean = float(returns.mean())
    return float(mean / std * (TRADING_DAYS**0.5))


def _annualized_excess(port_ret: pd.Series, bench_ret: pd.Series) -> float | None:
    """年化超额(几何超额年化)。"""
    if len(port_ret) < 2 or len(bench_ret) < 2:
        return None
    n = len(port_ret)
    port_ann = float((1.0 + port_ret).prod()) ** (TRADING_DAYS / n) - 1.0
    bench_ann = float((1.0 + bench_ret).prod()) ** (TRADING_DAYS / n) - 1.0
    return float(port_ann - bench_ann)


__all__: list[str] = [
    "TOTAL_RETURN_BENCH",
    "TYPE_TO_ASSET_CLASS",
    "PortfolioBacktestResult",
    "pick_benchmark",
    "portfolio_backtest",
]
