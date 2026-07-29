"""采集编排服务 + 调度器单测(P1-01d，§3.1.2 / §3.14 / §3.14.6)。

全 mock：DataSourceCoordinator + DistributedLock 注入 stub，DB 用真实 PG(标记 db)。
覆盖：带锁采集、未获锁跳过、APScheduler 作业注册。
"""

from __future__ import annotations

import pytest

from domain.scheduler import COLLECT_CRON, build_scheduler
from infra.lock import InMemoryLock


class _StubCoordinator:
    """返回固定数据的存根协调器(避免真实数据源)。"""

    class _Primary:
        source = "stub"

    def __init__(self) -> None:
        self.primary = self._Primary()

    def fetch(self, method: str, **kwargs):  # type: ignore[no-untyped-def]
        if method == "fetch_fund_list":
            return [{"code": "000001", "name": "华夏成长", "type_": "mixed"}]
        if method == "fetch_nav":
            return [
                {"code": kwargs.get("code"), "trade_date": "2025-07-28", "nav": 1.0, "acc_nav": 2.0}
            ]
        if method == "fetch_holdings":
            return [
                {"code": kwargs.get("code"), "report_date": "2024-03-31", "stock_code": "002025"}
            ]
        return []


class _CountingLock(InMemoryLock):
    """计数获锁次数的内存锁(测试防重调用)。"""

    def __init__(self) -> None:
        super().__init__()
        self.acquire_calls = 0

    def acquire(self, job: str, ttl: int = 3600) -> bool:
        self.acquire_calls += 1
        return super().acquire(job, ttl)


class TestScheduler:
    """§3.14.2 APScheduler 作业注册。"""

    def test_cron_is_weekday_18(self) -> None:
        """§3.14.2 工作日 18:00。"""
        assert COLLECT_CRON == "0 18 * * 1-5"

    def test_build_scheduler_registers_job(self) -> None:
        called: list[int] = []

        def _job() -> None:
            called.append(1)

        sched = build_scheduler(
            jobs=[{"id": "test", "func": _job, "cron": "0 18 * * 1-5", "args": []}]
        )
        sched.start()
        try:
            jobs = sched.get_jobs()
            assert len(jobs) == 1
            assert jobs[0].id == "test"
            # 确认 max_instances=1(§3.14.6 单实例不重叠)
            assert jobs[0].max_instances == 1
        finally:
            sched.shutdown(wait=False)


@pytest.mark.db
class TestCollectService:
    """§3.1.2 采集编排(带锁) + DB upsert 集成。"""

    @pytest.fixture()
    def engine(self, db_url: str):

        from sqlalchemy import create_engine

        import infra.db.models  # noqa: F401
        from infra.db import Base

        eng = create_engine(db_url)
        Base.metadata.drop_all(eng, checkfirst=True)
        Base.metadata.create_all(eng)
        yield eng
        Base.metadata.drop_all(eng)
        eng.dispose()

    def test_collect_fund_list_with_lock(self, engine) -> None:
        """采集名单：获锁 -> 清洗 -> upsert；写质量日志。"""
        from sqlalchemy.orm import Session

        from domain.collect_service import CollectService

        with Session(engine) as db:
            service = CollectService(db, coordinator=_StubCoordinator(), lock=_CountingLock())
            count = service.collect_fund_list()
            assert count == 1
            # 验证写入
            from sqlalchemy import text

            row = db.execute(text("SELECT name FROM funds WHERE code='000001'")).one()
            qcount = db.execute(text("SELECT count(*) FROM data_quality_log")).scalar()
        assert row[0] == "华夏成长"
        assert qcount == 1  # 质量日志已写

    def test_collect_skips_when_locked(self, engine) -> None:
        """锁已被占 -> 跳过，不采集(§3.14.6)。"""
        from sqlalchemy.orm import Session

        from domain.collect_service import CollectService
        from infra.lock import InMemoryLock

        lock = InMemoryLock()
        lock.acquire("collect_fund_list")  # 预占锁
        with Session(engine) as db:
            service = CollectService(db, coordinator=_StubCoordinator(), lock=lock)
            count = service.collect_fund_list()
        assert count == 0  # 跳过未采集

    def test_collect_all_aggregates(self, engine) -> None:
        """批量采集聚合各维度计数(§3.14.2)。"""
        from datetime import date

        from sqlalchemy.orm import Session

        from domain.collect_service import CollectService

        today = date.today().strftime("%Y%m%d")
        with Session(engine) as db:
            service = CollectService(db, coordinator=_StubCoordinator(), lock=InMemoryLock())
            result = service.collect_all(["000001"], start=today, end=today)
        assert result["funds"] == 1
        assert result["navs"] >= 1
