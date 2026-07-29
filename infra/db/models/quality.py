"""数据质量监控域 ORM 模型(技规§3.2 data_quality_log / 详设§3.1.4)。

§3.1.4：数据质量日志表，记录采集成功率/缺失/对账误差。
> 表结构来自技术规格§3.2(详设§2.20.3 仅列名，属 D2；此表 DDL 已在技规明确，部分解决 D2)。
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import TIMESTAMP, BigInteger, Boolean, Date, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from infra.db.base import Base


class DataQualityLog(Base):
    """数据质量日志表(技规§3.2 / §3.1.4)。

    采集任务结束写分片成功率/缺失天数/交叉验证误差(§3.1.8 质量聚合)。
    不可删改(可清理但保留摘要，§3.1.7)。
    """

    __tablename__ = "data_quality_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    entity: Mapped[str | None] = mapped_column(String(32))  # 采集实体(如 code 或 'all')
    check_date: Mapped[date | None] = mapped_column(Date)
    missing_count: Mapped[int | None] = mapped_column(Integer)
    anomaly_flag: Mapped[bool | None] = mapped_column(Boolean)
    cv_error: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))  # 交叉验证误差(>0.5%标红)
    source: Mapped[str | None] = mapped_column(String(32))
    as_of: Mapped[date | None] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
