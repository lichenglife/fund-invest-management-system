"""组合域 ORM 模型(详设§2.20.2：portfolios / portfolio_weights)。

严格对齐 DDL：portfolio_id VARCHAR(32) PK；source CHECK('template','manual','import')；
portfolio_weights 复合 PK(portfolio_id, code)，weight NUMERIC(8,4)。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import TIMESTAMP, CheckConstraint, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from infra.db.base import Base

_CODE_LEN = 12
_ACCT_LEN = 32
_PF_LEN = 32


class Portfolio(Base):
    """组合表(§2.20.2 portfolios)。account_id 关联模拟账户。"""

    __tablename__ = "portfolios"

    portfolio_id: Mapped[str] = mapped_column(String(_PF_LEN), primary_key=True)
    account_id: Mapped[str] = mapped_column(
        String(_ACCT_LEN),
        ForeignKey("paper_accounts.account_id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str | None] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("source IN ('template','manual','import')", name="ck_portfolios_source"),
    )


class PortfolioWeight(Base):
    """组合权重表(§2.20.2 portfolio_weights)。复合 PK(portfolio_id, code)。"""

    __tablename__ = "portfolio_weights"

    portfolio_id: Mapped[str] = mapped_column(
        String(_PF_LEN),
        ForeignKey("portfolios.portfolio_id", ondelete="CASCADE"),
        primary_key=True,
    )
    code: Mapped[str] = mapped_column(
        String(_CODE_LEN), ForeignKey("funds.code"), primary_key=True  # DDL 无 ON DELETE
    )
    weight: Mapped[float] = mapped_column(Numeric(8, 4), nullable=False)
