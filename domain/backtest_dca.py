"""定投回测(P1-07d，详设§3.5.8 / TP-04 §3.1 / CLAUDE.md §4 E3 红线)。

历史定投回放：按频率(weekly/monthly/quarterly)回放历史 NAV，累计投入/市值/成本摊薄。

E3 红线：
- 统一**后复权净值(adj_nav)**，删 DIVIDEND_MODE(后复权已含分红再投，不单独设)。
- ``final_val`` 扣**赎回费**后参与 IRR(闭锁 E3 漏计)。
- 防未来函数：用 shift(1) 对齐，窗口端点用实际交易日。

口径(TP-04 §3.1 _run_dca)：
- 申购费 ``BUY_FEE_RATE``(0.0015，按扣款金额计)。
- 赎回费 ``REDEEM_FEE_BY_HOLD``(阶梯，P1-07b 已实现)。
- IRR 用 xirr(不规则现金流)。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import pandas as pd
from scipy.optimize import brentq

logger = logging.getLogger(__name__)

#: 定投频率 -> resample 规则(TP-04 §3.1；pandas 2.2+ 用 ME 替代 M)。
FREQ_RULES: dict[str, str] = {
    "weekly": "W-MON",
    "monthly": "ME",
    "quarterly": "QE",
}

#: 申购费率(TP-04 §3.1，默认 0.15%)。
BUY_FEE_RATE = 0.0015


@dataclass(frozen=True)
class DcaResult:
    """定投回测结果(TP-04 §3.1)。"""

    cum_invest: float = 0.0  # 累计投入
    gross_value: float = 0.0  # 赎回前市值
    redeem_fee: float = 0.0  # 赎回费
    final_value: float = 0.0  # 扣费终值(E3)
    profit: float = 0.0  # 利润 = final_value - cum_invest
    irr: float | None = None  # 内部收益率(xirr)
    max_drawdown: float = 0.0  # 最大回撤(负值，E5)
    shares: float = 0.0  # 累计份额
    invest_count: int = 0  # 定投次数
    nav_curve: list[dict[str, Any]] = field(default_factory=list)  # 净值曲线

    def to_dict(self) -> dict[str, Any]:
        return {
            "cum_invest": self.cum_invest,
            "gross_value": self.gross_value,
            "redeem_fee": self.redeem_fee,
            "final_value": self.final_value,
            "profit": self.profit,
            "irr": self.irr,
            "max_drawdown": self.max_drawdown,
            "shares": self.shares,
            "invest_count": self.invest_count,
            "nav_curve": self.nav_curve,
        }


def run_dca(
    nav: pd.Series,
    *,
    freq: str = "monthly",
    amount: float = 1000.0,
    buy_fee: float = BUY_FEE_RATE,
    redeem_fee_rate: float | None = None,
) -> DcaResult:
    """定投回测(TP-04 §3.1 _run_dca)。

    Args:
        nav: 后复权净值序列(adj_nav，E3；index=日期)。
        freq: 定投频率(weekly/monthly/quarterly)。
        amount: 每期定投金额(元)。
        buy_fee: 申购费率(默认 0.15%)。
        redeem_fee_rate: 赎回费率；None 按持有时长算(TP-04 REDEEM_FEE_BY_HOLD)。
    Returns:
        DcaResult。
    """
    if nav is None or len(nav) < 2:
        return DcaResult()

    freq_rule = FREQ_RULES.get(freq, FREQ_RULES["monthly"])
    # 按频率 resample 取期末净值(TP-04 §3.1)
    nav_resampled = nav.resample(freq_rule).last().ffill()

    shares = 0.0
    cum_cost = 0.0
    cash_flow: list[tuple[pd.Timestamp, float]] = []
    nav_curve: list[dict[str, Any]] = []

    for day, nav_i in zip(nav_resampled.index, nav_resampled.values, strict=False):
        nav_val = float(nav_i)
        if nav_val <= 0:
            continue  # §4 红线：NAV<=0 不崩溃
        # 申购扣费后份额(TP-04: buy = amount / (nav_i * (1 + BUY_FEE_RATE)))
        buy_shares = amount / (nav_val * (1.0 + buy_fee))
        shares += buy_shares
        cum_cost += amount
        cash_flow.append((day, -amount))
        nav_curve.append({"date": day.isoformat(), "nav": nav_val, "shares": shares})

    if shares == 0 or cum_cost == 0:
        return DcaResult()

    # 赎回前市值
    gross_val = shares * float(nav_resampled.values[-1])

    # 赎回费(E3 final_val 扣赎回费)
    from domain.paper import redeem_fee

    # 持有时长(首笔到末日)
    if len(nav_resampled) > 0:
        hold_days = (nav_resampled.index[-1] - nav_resampled.index[0]).days
    else:
        hold_days = 0
    fee_rate = redeem_fee_rate if redeem_fee_rate is not None else redeem_fee(hold_days)
    fee_amount = gross_val * fee_rate
    final_val = gross_val - fee_amount

    # IRR(xirr，不规则现金流)
    # 最后一笔现金流 = 赎回终值(正)
    cash_flow.append((nav_resampled.index[-1], final_val))
    irr_val = _xirr(cash_flow)

    # 最大回撤(E5 负值)
    max_dd = _max_drawdown(nav_resampled)

    return DcaResult(
        cum_invest=cum_cost,
        gross_value=gross_val,
        redeem_fee=fee_amount,
        final_value=final_val,
        profit=final_val - cum_cost,
        irr=irr_val,
        max_drawdown=max_dd,
        shares=shares,
        invest_count=len(cash_flow) - 1,  # 排除赎回笔
        nav_curve=nav_curve,
    )


def _xirr(cash_flows: list[tuple[pd.Timestamp, float]]) -> float | None:
    """XIRR(不规则现金流内部收益率)。

    用 brentq 求解 NPV=0 的年化收益率。

    Args:
        cash_flows: [(date, amount)]，amount 负=流出，正=流入。
    Returns:
        年化 IRR；无解返回 None。
    """
    if len(cash_flows) < 2:
        return None

    # 转为相对天数(years)
    dates = [cf[0] for cf in cash_flows]
    amounts = [cf[1] for cf in cash_flows]
    t0 = dates[0]
    years = [(d - t0).days / 365.25 for d in dates]

    def npv(rate: float) -> float:
        return float(sum(a / ((1.0 + rate) ** t) for a, t in zip(amounts, years, strict=False)))

    # 判断有解：现金流需有正有负
    if all(a >= 0 for a in amounts) or all(a <= 0 for a in amounts):
        return None

    try:
        # brentq 在 [-0.99, 10] 求解 NPV=0
        return float(brentq(npv, -0.99, 10.0))
    except (ValueError, RuntimeError):
        return None


def _max_drawdown(nav: pd.Series) -> float:
    """最大回撤(负值，E5)。"""
    returns = nav.pct_change().dropna()
    if len(returns) < 2:
        return 0.0
    cum = (1 + returns).cumprod()
    peak = cum.cummax()
    dd = (cum - peak) / peak
    return float(dd.min()) if len(dd) > 0 else 0.0


__all__: list[str] = ["FREQ_RULES", "BUY_FEE_RATE", "DcaResult", "run_dca"]
