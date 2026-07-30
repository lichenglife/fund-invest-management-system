"""基金分红域 ORM 模型(技规§3.2 fund_dividends / 详设§3.5.4 分红处理)。

> 表结构来自技术规格§3.2(详设§2.20.3 仅列名，属 D2；此表 DDL 已在技规明确)。
> E3 红线：统一后复权净值(adj_nav)已含分红再投，删 DIVIDEND_MODE；
> 本表记录历史分红(除息日/每份分红)，供 run_dividend 调整持仓份额(单位净值成交场景)。
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from infra.db.base import Base


class FundDividend(Base):
    """基金分红表(技规§3.2 / §3.5.4)。

    Attributes:
        code: 基金代码。
        ex_date: 除息日。
        div_per_unit: 每份分红(元)。
        source: 数据来源。
    """

    __tablename__ = "fund_dividends"

    code: Mapped[str] = mapped_column(String(12), primary_key=True)
    ex_date: Mapped[date] = mapped_column(Date, primary_key=True)
    div_per_unit: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    source: Mapped[str | None] = mapped_column(String(32))
