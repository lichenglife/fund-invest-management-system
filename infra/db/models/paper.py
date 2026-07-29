"""模拟交易域 ORM 模型(详设§2.20.2：paper_accounts / paper_positions / paper_trades)。

严格对齐 DDL：account_id VARCHAR(32) PK；init_capital 默认 1000000；
paper_trades.trade_id BIGSERIAL；side CHECK('buy','sell')。
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    TIMESTAMP,
    BigInteger,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Numeric,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from infra.db.base import Base

_CODE_LEN = 12
_ACCT_LEN = 32


class PaperAccount(Base):
    """模拟账户表(§2.20.2 paper_accounts)。MVP 单用户，不连通实盘(§10 非目标)。"""

    __tablename__ = "paper_accounts"

    account_id: Mapped[str] = mapped_column(String(_ACCT_LEN), primary_key=True)
    init_capital: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, server_default=text("1000000"), default=Decimal("1000000")
    )
    cash: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )


class PaperPosition(Base):
    """模拟持仓表(§2.20.2 paper_positions)。复合 PK(account_id, code)。"""

    __tablename__ = "paper_positions"

    account_id: Mapped[str] = mapped_column(
        String(_ACCT_LEN),
        ForeignKey("paper_accounts.account_id", ondelete="CASCADE"),
        primary_key=True,
    )
    code: Mapped[str] = mapped_column(
        String(_CODE_LEN), ForeignKey("funds.code", ondelete="CASCADE"), primary_key=True
    )
    shares: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    cost: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PaperTrade(Base):
    """模拟交易流水表(§2.20.2 paper_trades)。trade_id BIGSERIAL；side buy/sell。"""

    __tablename__ = "paper_trades"

    trade_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    account_id: Mapped[str] = mapped_column(
        String(_ACCT_LEN),
        ForeignKey("paper_accounts.account_id", ondelete="CASCADE"),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(
        String(_CODE_LEN),
        ForeignKey("funds.code"),
        nullable=False,  # DDL 无 ON DELETE，默认 NO ACTION
    )
    side: Mapped[str] = mapped_column(String(4), nullable=False)
    shares: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    nav: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("side IN ('buy','sell')", name="ck_paper_trades_side"),
        Index("ix_trades_account", "account_id", "trade_date"),
    )
