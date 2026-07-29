"""采集持久化层(P1-01c，详设§3.1.2 增量写入 / §3.14.5 幂等)。

幂等 upsert：按主键 ON CONFLICT DO UPDATE，重跑不产生重复行(§3.14.5)。
事务边界：批量写要么全成功要么全失败(§8.4)；缓存与 DB 不一致以 DB 为准(ADR-002)。
质量日志：写 data_quality_log(§3.1.4 / §3.1.8 质量聚合)。

> 写操作须在事务边界内(§8.4)；由调用方(P1-01d worker)控制调度。
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from domain.collect import NavRecord
from infra.db.models import Fund, Holding, Nav
from infra.db.models.quality import DataQualityLog

logger = logging.getLogger(__name__)

#: 批量写阈值(单事务，避免过大)。
BATCH_SIZE = 500


def upsert_funds(db: Session, records: list[dict[str, Any]]) -> int:
    """幂等 upsert 基金名单(§3.14.5，PK=code)。返回 upsert 行数。"""
    if not records:
        return 0
    rows = [
        {
            "code": r["code"],
            "name": r["name"],
            "type": r["type_"],
            "source": r.get("source", "AkShare"),
            "as_of": date.today(),
        }
        for r in records
    ]
    stmt = pg_insert(Fund).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=[Fund.code],
        set_={
            "name": stmt.excluded.name,
            "type": stmt.excluded.type,
            "source": stmt.excluded.source,
            "as_of": stmt.excluded.as_of,
            "updated_at": func.now(),
        },
    )
    db.execute(stmt)
    db.commit()
    logger.info("upsert.funds", extra={"action": "upsert", "count": len(rows)})
    return len(rows)


def upsert_navs(db: Session, records: list[NavRecord]) -> int:
    """幂等 upsert 净值(§3.14.5，PK=code+trade_date)。返回 upsert 行数。

    Args:
        records: clean_nav() 返回的清洗记录。
    """
    if not records:
        return 0
    total = 0
    for i in range(0, len(records), BATCH_SIZE):
        batch = records[i : i + BATCH_SIZE]
        rows = [_nav_row(r) for r in batch]
        stmt = pg_insert(Nav).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=[Nav.code, Nav.trade_date],
            set_={
                "nav": stmt.excluded.nav,
                "acc_nav": stmt.excluded.acc_nav,
                "adj_nav": stmt.excluded.adj_nav,
                "is_estimate": stmt.excluded.is_estimate,
                "source": stmt.excluded.source,
                "as_of": stmt.excluded.as_of,
            },
        )
        db.execute(stmt)
        total += len(rows)
    db.commit()
    logger.info("upsert.navs", extra={"action": "upsert", "count": total})
    return total


def upsert_holdings(db: Session, records: list[dict[str, Any]]) -> int:
    """幂等 upsert 重仓股(§3.14.5，PK=code+report_date+stock_code)。"""
    if not records:
        return 0
    rows = [
        {
            "code": r["code"],
            "report_date": r["report_date"],
            "stock_code": r["stock_code"],
            "stock_name": r.get("stock_name"),
            "weight": r.get("weight"),
            "source": r.get("source", "AkShare"),
            "as_of": date.today(),
        }
        for r in records
    ]
    stmt = pg_insert(Holding).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=[Holding.code, Holding.report_date, Holding.stock_code],
        set_={
            "stock_name": stmt.excluded.stock_name,
            "weight": stmt.excluded.weight,
            "source": stmt.excluded.source,
            "as_of": stmt.excluded.as_of,
        },
    )
    db.execute(stmt)
    db.commit()
    logger.info("upsert.holdings", extra={"action": "upsert", "count": len(rows)})
    return len(rows)


def write_quality_log(
    db: Session,
    *,
    entity: str,
    missing_count: int = 0,
    anomaly_flag: bool = False,
    cv_error: Decimal | None = None,
    source: str = "AkShare",
    note: str | None = None,
) -> None:
    """写数据质量日志(§3.1.4 / §3.1.8)。不可删改(§3.1.7)。"""
    log = DataQualityLog(
        entity=entity,
        check_date=date.today(),
        missing_count=missing_count,
        anomaly_flag=anomaly_flag,
        cv_error=cv_error,
        source=source,
        as_of=date.today(),
        note=note,
    )
    db.add(log)
    db.commit()
    logger.info(
        "quality.log_written",
        extra={"action": "quality_log", "entity": entity, "missing": missing_count},
    )


def _nav_row(r: NavRecord) -> dict[str, Any]:
    """NavRecord -> navs 表行(§2.20.2)。adj_nav 回退见 clean_nav(D6)。"""
    adj = r.get("adj_nav")
    return {
        "code": r["code"],
        "trade_date": r["trade_date"],
        "nav": r["nav"],
        "acc_nav": r.get("acc_nav"),
        "adj_nav": adj if adj is not None else r["nav"],  # NOT NULL 兜底
        "is_estimate": r.get("is_estimate", False),
        "source": r.get("source", "AkShare"),
        "as_of": date.today(),
    }


__all__: list[str] = [
    "BATCH_SIZE",
    "upsert_funds",
    "upsert_navs",
    "upsert_holdings",
    "write_quality_log",
]
