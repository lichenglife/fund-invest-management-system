"""并发写冲突测试(P1-01c 补测，§8.4 事务原子性 / ON CONFLICT 幂等)。

多线程同时 upsert 同一 code 的净值，验证：
- 不死锁(ON CONFLICT DO UPDATE 天然避免主键冲突)
- 无脏数据(最终状态一致，非半量)
- 无重复行(幂等)
"""

from __future__ import annotations

import threading
from datetime import date, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from domain.collect import clean_nav
from infra.collect_repo import upsert_funds, upsert_navs

pytestmark = pytest.mark.db


def _nav_records(code: str, days: int) -> list[dict[str, object]]:
    """生成 N 天净值记录。"""
    base = date(2025, 1, 1)
    return [
        {
            "code": code,
            "trade_date": (base + timedelta(days=i)).isoformat(),
            "nav": 1.0 + i * 0.001,
            "acc_nav": 2.0 + i * 0.001,
        }
        for i in range(days)
    ]


class TestConcurrentUpsert:
    """§8.4 并发写：ON CONFLICT 不死锁、无脏数据、无重复。"""

    def test_concurrent_same_code_no_deadlock(self, engine) -> None:
        """多线程同时 upsert 同一 code -> 不死锁，最终一致(无重复)。"""
        with Session(engine) as db:
            upsert_funds(db, [{"code": "000001", "name": "x", "type_": "mixed"}])

        records = clean_nav(_nav_records("000001", 50), source="AkShare")
        errors: list[Exception] = []

        def _worker() -> None:
            try:
                with Session(engine) as db:
                    upsert_navs(db, records)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        # 4 线程并发 upsert 相同数据
        threads = [threading.Thread(target=_worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 无异常(不死锁/不冲突)
        assert errors == [], f"并发写出现异常: {errors}"
        # 最终一致：50 条，无重复(幂等)
        with Session(engine) as db:
            cnt = db.execute(text("SELECT count(*) FROM navs WHERE code='000001'")).scalar()
        assert cnt == 50, f"并发后行数异常: {cnt}(期望 50)"

    def test_concurrent_different_codes_isolated(self, engine) -> None:
        """多线程 upsert 不同 code -> 互不干扰，各自完整。"""
        with Session(engine) as db:
            upsert_funds(
                db,
                [
                    {"code": "000001", "name": "a", "type_": "mixed"},
                    {"code": "000002", "name": "b", "type_": "mixed"},
                ],
            )

        errors: list[Exception] = []

        def _worker(code: str) -> None:
            try:
                records = clean_nav(_nav_records(code, 30), source="AkShare")
                with Session(engine) as db:
                    upsert_navs(db, records)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [
            threading.Thread(target=_worker, args=("000001",)),
            threading.Thread(target=_worker, args=("000002",)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"并发写异常: {errors}"
        with Session(engine) as db:
            c1 = db.execute(text("SELECT count(*) FROM navs WHERE code='000001'")).scalar()
            c2 = db.execute(text("SELECT count(*) FROM navs WHERE code='000002'")).scalar()
        assert c1 == 30 and c2 == 30, f"并发隔离失败: {c1}/{c2}"
