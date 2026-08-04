"""采集 upsert 持久化集成测试(P1-01c，详设§3.1.2 / §3.14.5 幂等)。

DB 集成：用 compose PG 实测 ON CONFLICT 幂等 upsert + 质量日志。
标记 db，无 PG 跳过(``pytest -m "not db"``)。
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from domain.collect import clean_holdings, clean_nav
from infra.collect_repo import upsert_funds, upsert_holdings, upsert_navs, write_quality_log

pytestmark = pytest.mark.db


class TestUpsertFunds:
    def test_insert_then_update_idempotent(self, engine) -> None:
        """§3.14.5：upsert 幂等，重跑不产生重复行。"""
        funds = [
            {"code": "000001", "name": "华夏成长", "type_": "mixed", "source": "AkShare"},
            {"code": "000002", "name": "华夏大盘", "type_": "mixed", "source": "AkShare"},
        ]
        with Session(engine) as db:
            n1 = upsert_funds(db, funds)
            assert n1 == 2
        # 重跑(改名) -> 更新而非插入
        funds[0]["name"] = "华夏成长(新)"
        with Session(engine) as db:
            n2 = upsert_funds(db, funds)
            assert n2 == 2
        with Session(engine) as db:
            row = db.execute(text("SELECT name FROM funds WHERE code='000001'")).one()
            cnt = db.execute(text("SELECT count(*) FROM funds")).scalar()
        assert row[0] == "华夏成长(新)"  # 已更新
        assert cnt == 2  # 无重复


class TestUpsertNavs:
    def test_idempotent_and_adj_nav_notnull(self, engine) -> None:
        """§3.14.5 幂等 + adj_nav NOT NULL 兜底(D6)。"""
        # 先建基金(满足 FK)
        with Session(engine) as db:
            upsert_funds(db, [{"code": "000001", "name": "华夏成长", "type_": "mixed"}])

        raw = [
            {
                "code": "000001",
                "trade_date": "2025-07-28",
                "nav": 1.308,
                "acc_nav": 2.678,
                "adj_nav": None,
            },
        ]
        cleaned = clean_nav(raw, source="AkShare")
        assert cleaned[0]["adj_nav"] == Decimal("2.678")  # 回退 acc_nav

        with Session(engine) as db:
            n = upsert_navs(db, cleaned)
            assert n == 1
            # 重跑 -> 幂等
            n2 = upsert_navs(db, cleaned)
            assert n2 == 1
            row = db.execute(
                text("SELECT nav, acc_nav, adj_nav, source FROM navs WHERE code='000001'")
            ).one()
            cnt = db.execute(text("SELECT count(*) FROM navs WHERE code='000001'")).scalar()

        assert row[0] == Decimal("1.308")
        assert row[1] == Decimal("2.678")
        assert row[2] == Decimal("2.678")  # adj_nav = acc_nav(D6 回退)，非空
        assert row[3] == "AkShare"
        assert cnt == 1  # 幂等无重复

    def test_batch_size(self, engine) -> None:
        """批量写(BATCH_SIZE=500)正确分批。"""
        with Session(engine) as db:
            upsert_funds(db, [{"code": "000001", "name": "x", "type_": "mixed"}])
        raw = [
            {"code": "000001", "trade_date": f"2024-01-{d:02d}", "nav": 1.0, "acc_nav": 2.0}
            for d in range(1, 29)  # 28 条
        ]
        cleaned = clean_nav(raw)
        with Session(engine) as db:
            n = upsert_navs(db, cleaned)
            assert n == 28


class TestUpsertHoldings:
    def test_idempotent_composite_pk(self, engine) -> None:
        """§3.14.5：复合 PK 幂等。"""
        with Session(engine) as db:
            upsert_funds(db, [{"code": "000001", "name": "x", "type_": "mixed"}])
        raw = [
            {
                "code": "000001",
                "report_date": "2024-03-31",
                "stock_code": "002025",
                "weight": 0.0346,
            },
        ]
        cleaned = clean_holdings(raw)
        with Session(engine) as db:
            upsert_holdings(db, cleaned)
            upsert_holdings(db, cleaned)  # 重跑
            cnt = db.execute(text("SELECT count(*) FROM holdings")).scalar()
        assert cnt == 1


class TestQualityLog:
    def test_write_quality_log(self, engine) -> None:
        """§3.1.4：质量日志写入 data_quality_log。"""
        with Session(engine) as db:
            write_quality_log(
                db,
                entity="000001",
                missing_count=2,
                anomaly_flag=True,
                cv_error=Decimal("0.0034"),
                source="AkShare",
                note="测试缺失",
            )
            row = db.execute(
                text(
                    "SELECT entity, missing_count, anomaly_flag, cv_error, note "
                    "FROM data_quality_log WHERE entity='000001'"
                )
            ).one()
            cnt = db.execute(text("SELECT count(*) FROM data_quality_log")).scalar()

        assert row[0] == "000001"
        assert row[1] == 2
        assert row[2] is True
        assert row[3] == Decimal("0.0034")
        assert row[4] == "测试缺失"
        assert cnt == 1
