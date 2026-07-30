"""模拟交易请求/响应模型(P1-07a，§3.5.6 / §2.21.2)。"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class BuyRequest(BaseModel):
    """POST /api/paper/buy(§2.21.2)。"""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(description="基金代码")
    amount: Decimal | None = Field(default=None, description="买入金额(元)，与 shares 二选一")
    shares: Decimal | None = Field(default=None, description="买入份额，与 amount 二选一")
    trade_date: str | None = Field(default=None, description="交易日期(YYYY-MM-DD)")


class SellRequest(BaseModel):
    """POST /api/paper/sell(§2.21.2)。"""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(description="基金代码")
    shares: Decimal | None = Field(default=None, description="卖出份额，与 amount 二选一")
    amount: Decimal | None = Field(default=None, description="卖出金额，与 shares 二选一")
    trade_date: str | None = Field(default=None, description="交易日期(YYYY-MM-DD)")


class ResetRequest(BaseModel):
    """POST /api/paper/reset(§3.5.7 二次确认)。"""

    model_config = ConfigDict(extra="forbid")

    confirm: bool = Field(default=False, description="二次确认(必须 True)")
