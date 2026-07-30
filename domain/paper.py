"""分红复权与赎回费(P1-07b，详设§3.5.4 / TP-04 §3.1 / CLAUDE.md §4 E3 红线)。

E3 红线：统一**后复权净值(adj_nav)**，删 ``DIVIDEND_MODE``，杜绝分红双重计。
后复权净值已含分红再投，回测/盈亏用 adj_nav；交易成交用单位净值(nav)。

分红复权(``run_dividend``)：
- 单位净值成交场景：分红除息日，持仓份额按 ``div_per_unit / ex_nav`` 调整(分红再投)。
- 后复权净值场景：adj_nav 已含分红，不单独调整(删 DIVIDEND_MODE, E3)。

赎回费(TP-04 §3.1 ``REDEEM_FEE_BY_HOLD``)：
- 按持有时长阶梯；``final_val = gross_val * (1 - fee)`` 参与 IRR(E3 漏计修复)。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

#: 赎回费阶梯(按持有时长，TP-04 §3.1)。
REDEEM_FEE_BY_HOLD: dict[str, float] = {
    "d7": 0.015,  # <7 日
    "d30": 0.005,  # 7-30 日
    "d365": 0.0025,  # 30-365 日
    "gt365": 0.0,  # >365 日
}

#: 默认赎回费(取 >365 日档，TP-04)。
DEF_REDEEM_FEE = 0.0


def redeem_fee(hold_days: int) -> float:
    """按持有时长算赎回费率(TP-04 §3.1 REDEEM_FEE_BY_HOLD)。

    Args:
        hold_days: 持有天数。
    Returns:
        赎回费率(小数)。
    """
    if hold_days < 7:
        return REDEEM_FEE_BY_HOLD["d7"]
    if hold_days < 30:
        return REDEEM_FEE_BY_HOLD["d30"]
    if hold_days < 365:
        return REDEEM_FEE_BY_HOLD["d365"]
    return REDEEM_FEE_BY_HOLD["gt365"]


def final_value(gross_value: Decimal, hold_days: int) -> tuple[Decimal, Decimal]:
    """扣赎回费终值(闭锁 E3 漏计)。

    Args:
        gross_value: 赎回前市值。
        hold_days: 持有天数。
    Returns:
        (final_value, redeem_fee_amount)。
    """
    fee_rate = Decimal(str(redeem_fee(hold_days)))
    fee_amount = gross_value * Decimal(str(fee_rate))
    return gross_value - fee_amount, fee_amount


def run_dividend(
    shares: Decimal,
    div_per_unit: Decimal,
    ex_nav: Decimal,
    *,
    mode: str = "reinvest",
) -> dict[str, Any]:
    """分红复权调整份额(§3.5.4 / TP-04)。

    单位净值成交场景：分红除息日，按 ``div_per_unit / ex_nav`` 算新增份额(再投)。
    > E3：后复权净值(adj_nav)已含分红再投，本函数仅用于单位净值成交场景的份额调整；
    > 回测统一用 adj_nav 时不调用本函数(删 DIVIDEND_MODE, E3)。

    Args:
        shares: 分红前持仓份额。
        div_per_unit: 每份分红(元)。
        ex_nav: 除息日单位净值。
        mode: reinvest(再投，默认)/cash(现金分红)。
    Returns:
        {shares_after, cash_dividend, new_shares}。
    """
    cash_dividend = shares * div_per_unit  # 现金分红总额
    if mode == "cash":
        return {
            "shares_after": shares,
            "cash_dividend": cash_dividend,
            "new_shares": Decimal("0"),
            "mode": "cash",
        }
    # reinvest：现金分红按除息日净值再投为份额
    if ex_nav <= 0:
        return {
            "shares_after": shares,
            "cash_dividend": cash_dividend,
            "new_shares": Decimal("0"),
            "mode": "reinvest",
            "note": "ex_nav<=0, 跳过再投(§4 红线不崩溃)",
        }
    new_shares = cash_dividend / ex_nav
    return {
        "shares_after": shares + new_shares,
        "cash_dividend": cash_dividend,
        "new_shares": new_shares,
        "mode": "reinvest",
    }


__all__: list[str] = [
    "REDEEM_FEE_BY_HOLD",
    "DEF_REDEEM_FEE",
    "redeem_fee",
    "final_value",
    "run_dividend",
]
