"""基金域 ORM 模型(详设§2.20.2 核心表 DDL：funds / navs / holdings / scores / research_metrics)。

严格对齐 DDL：字段名/类型/精度/FK/索引/CHECK 一致。
- 金额 NUMERIC(18,4)；比率/权重 NUMERIC(12,6) / NUMERIC(8,4)。
- 时间 TIMESTAMPTZ(默认 now())；溯源字段 source/as_of。
- 分红/经理等其余基金表见 §2.20.3，字段未定义，搁置(见 docs/DEFERRED.md)。
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import TIMESTAMP, Boolean, Date, ForeignKey, Index, Numeric, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from infra.db.base import Base

# 通用列长度(对齐 DDL)
_CODE_LEN = 12
_NAME_LEN = 64
_SOURCE_LEN = 32


class Fund(Base):
    """基金基础信息表(§2.20.2 funds)。"""

    __tablename__ = "funds"

    code: Mapped[str] = mapped_column(String(_CODE_LEN), primary_key=True)
    name: Mapped[str] = mapped_column(String(_NAME_LEN), nullable=False)
    # ``type`` 是 Python 内置，属性名用 type_ 映射到 type 列(§2.20.2)
    type_: Mapped[str] = mapped_column("type", String(16), nullable=False)
    sub_type: Mapped[str | None] = mapped_column(String(32))
    theme: Mapped[str | None] = mapped_column(String(32))
    style: Mapped[str | None] = mapped_column(String(16))
    launch_date: Mapped[date | None] = mapped_column(Date)
    source: Mapped[str] = mapped_column(String(_SOURCE_LEN), nullable=False)
    as_of: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (Index("ix_funds_type_theme", "type", "theme"),)


class Nav(Base):
    """基金日频净值表(§2.20.2 navs)。

    > DDL 给定 ``PARTITION BY RANGE (trade_date)`` 但未定义子分区；分区策略属
    > 运维层(§2.12，pg_partman/手动按年)，见 docs/DEFERRED.md。此处先建普通表，
    > 保证 PK/FK/索引正确，分区声明后续迁移补。
    """

    __tablename__ = "navs"

    code: Mapped[str] = mapped_column(
        String(_CODE_LEN), ForeignKey("funds.code", ondelete="CASCADE"), primary_key=True
    )
    trade_date: Mapped[date] = mapped_column(Date, primary_key=True)
    nav: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    acc_nav: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    adj_nav: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    is_estimate: Mapped[bool] = mapped_column(Boolean, server_default=text("false"), default=False)
    source: Mapped[str] = mapped_column(String(_SOURCE_LEN), nullable=False)
    as_of: Mapped[date] = mapped_column(Date, nullable=False)

    __table_args__ = (Index("ix_navs_date", "trade_date"),)


class Holding(Base):
    """基金重仓股表(§2.20.2 holdings)。"""

    __tablename__ = "holdings"

    code: Mapped[str] = mapped_column(
        String(_CODE_LEN), ForeignKey("funds.code", ondelete="CASCADE"), primary_key=True
    )
    report_date: Mapped[date] = mapped_column(Date, primary_key=True)
    stock_code: Mapped[str] = mapped_column(String(_CODE_LEN), primary_key=True)
    stock_name: Mapped[str | None] = mapped_column(String(_NAME_LEN))
    weight: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    source: Mapped[str] = mapped_column(String(_SOURCE_LEN), nullable=False)
    as_of: Mapped[date] = mapped_column(Date, nullable=False)


class Score(Base):
    """五因子评分表(§2.20.2 scores)。

    口径红线(CLAUDE.md §4，E4/E5 闭环)：五因子 = ``ret/risk/perf/scale/manager``，
    ``ret`` 权重 20。``weights``/``factors`` 为 JSONB，结构见 TP-01 §3.1。

    > 注：§2.20.2 DDL 注释与 §2.21.2 示例仍为旧口径 ``ret/risk/style/cost/scale``
    > (E4/E5 修订前)；表结构(JSONB)不变，注释口径以 CLAUDE.md §4 红线为准。
    > 见 docs/DEFERRED.md「D-口径冲突」。
    """

    __tablename__ = "scores"

    code: Mapped[str] = mapped_column(
        String(_CODE_LEN), ForeignKey("funds.code", ondelete="CASCADE"), primary_key=True
    )
    window: Mapped[str] = mapped_column(String(8), server_default=text("'3y'"), default="3y")
    weights: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    composite: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    factors: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    as_of: Mapped[date] = mapped_column(Date, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ResearchMetric(Base):
    """研究指标表(§2.20.2 research_metrics)。

    PEG/ERP 为代理指标，``peg_available``/``erp_available`` 标注可用性，
    ``cv_flag`` 交叉验证标志(§3.3.7 / TP-01)；未定义口径经 RESEARCH_PROXY_GUARD(40301)。
    """

    __tablename__ = "research_metrics"

    code: Mapped[str] = mapped_column(
        String(_CODE_LEN), ForeignKey("funds.code", ondelete="CASCADE"), primary_key=True
    )
    alpha: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    beta: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    tracking_error: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    info_ratio: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    peg: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    erp: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    peg_available: Mapped[bool] = mapped_column(
        Boolean, server_default=text("false"), default=False
    )
    erp_available: Mapped[bool] = mapped_column(
        Boolean, server_default=text("false"), default=False
    )
    cv_flag: Mapped[bool] = mapped_column(Boolean, server_default=text("false"), default=False)
    as_of: Mapped[date] = mapped_column(Date, nullable=False)
