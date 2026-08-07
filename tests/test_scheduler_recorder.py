"""record_job_run 执行记录落库测试(详设§3.14.3 scheduler_jobs / §3.14.5 失败告警)。

验证：
- 开始即写 ``status=running`` 行(可被其他会话查到 -> 独立 session 已提交)。
- 正常退出写 ``success`` + ``result_summary`` + ``finished_at`` + ``duration_ms``。
- 异常写 ``failed`` + ``error``(摘要，不含堆栈 §9)并 **re-raise**(§3.14.5)。
- 业务事务回滚不影响执行记录(record_job_run 用独立 session)。
- 超长 ``error`` 截断到 ``ERROR_MAX_LEN``。
- ``session_factory`` 可注入(测试隔离，懒导入 infra)。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from domain.scheduler import ERROR_MAX_LEN, SessionFactory, record_job_run
from infra.db.models.scheduler import SchedulerJob


@pytest.mark.db
class TestRecordJobRun:
    """record_job_run 落库 §3.14.3 / §3.14.5。"""

    @pytest.fixture()
    def sf(self, engine: Engine) -> SessionFactory:
        """绑定测试引擎的会话工厂(注入 record_job_run，替代默认 SessionLocal)。"""
        return sessionmaker(bind=engine, autocommit=False, autoflush=False)

    @staticmethod
    def _rows(engine: Engine) -> list[SchedulerJob]:
        """读取全部 scheduler_jobs 行(独立会话，按 id 升序)。"""
        with Session(bind=engine) as db:
            return list(db.execute(select(SchedulerJob).order_by(SchedulerJob.id)).scalars().all())

    def test_success_records_summary(self, sf: SessionFactory, engine: Engine) -> None:
        """正常退出：success + result_summary + finished_at + duration_ms(§3.14.3)。"""
        before = datetime.now(UTC)
        with record_job_run(
            "collect_all",
            "增量采集",
            trigger="manual",
            args={"codes": ["000001"]},
            session_factory=sf,
        ) as run:
            run.result_summary = {"funds": 3, "navs": 12}

        rows = self._rows(engine)
        assert len(rows) == 1
        row = rows[0]
        assert row.job_id == "collect_all"
        assert row.job_name == "增量采集"
        assert row.trigger == "manual"
        assert row.status == "success"
        assert row.args == {"codes": ["000001"]}
        assert row.result_summary == {"funds": 3, "navs": 12}
        assert row.error is None
        assert row.finished_at is not None
        assert row.duration_ms is not None and row.duration_ms >= 0
        assert row.started_at is not None
        assert row.started_at >= before - timedelta(seconds=1)

    def test_failed_records_error_and_reraises(self, sf: SessionFactory, engine: Engine) -> None:
        """异常：failed + error 摘要(不含堆栈 §9) + re-raise(§3.14.5)。"""
        with (
            pytest.raises(RuntimeError, match="boom"),
            record_job_run("fund_recalc", "指标重算", trigger="cron", session_factory=sf) as run,
        ):
            _ = run  # 句柄可用
            raise RuntimeError("boom at step 3")

        rows = self._rows(engine)
        assert len(rows) == 1
        row = rows[0]
        assert row.status == "failed"
        assert row.result_summary is None
        assert row.error is not None and "boom at step 3" in row.error
        assert row.finished_at is not None
        assert row.duration_ms is not None and row.duration_ms >= 0

    def test_running_row_committed_during_execution(
        self, sf: SessionFactory, engine: Engine
    ) -> None:
        """开始即写 running 行并已提交(独立 session；其他会话可查到)(§3.14.3)。"""
        with record_job_run("collect_all", session_factory=sf) as run:
            assert run.job_pk is not None
            rows = self._rows(engine)
            assert len(rows) == 1
            assert rows[0].status == "running"
            assert rows[0].finished_at is None
            assert rows[0].duration_ms is None
            run.result_summary = {"ok": True}

        # 正常退出后转 success
        assert self._rows(engine)[0].status == "success"

    def test_error_truncated_to_max_len(self, sf: SessionFactory, engine: Engine) -> None:
        """超长 error 截断到 ERROR_MAX_LEN(§9 不存完整堆栈)。"""
        long_msg = "x" * (ERROR_MAX_LEN + 500)
        with pytest.raises(ValueError), record_job_run("job_trunc", session_factory=sf):
            raise ValueError(long_msg)

        row = self._rows(engine)[0]
        assert row.error is not None
        assert len(row.error) == ERROR_MAX_LEN
        assert row.error == long_msg[:ERROR_MAX_LEN]

    def test_record_survives_inner_business_rollback(
        self, sf: SessionFactory, engine: Engine
    ) -> None:
        """执行记录独立提交：with 块内业务事务回滚不影响已落库行(§3.14.3 设计要点)。"""
        with record_job_run("collect_all", session_factory=sf) as run:
            # 模拟业务事务回滚(采集中途业务失败)
            with Session(bind=engine) as biz:
                biz.add(SchedulerJob(job_id="phantom_rollback", status="running"))
                biz.rollback()
            # 执行记录 running 行仍存在(由 sf 独立提交，未受业务回滚影响)
            rows = self._rows(engine)
            assert all(r.job_id != "phantom_rollback" for r in rows)
            assert rows[0].status == "running"
            run.result_summary = {"k": 1}

        rows = self._rows(engine)
        assert len(rows) == 1
        assert rows[0].job_id == "collect_all"
        assert rows[0].status == "success"

    def test_default_trigger_is_cron(self, sf: SessionFactory, engine: Engine) -> None:
        """未指定 trigger 默认 cron(定时来源)(§3.14.2)。"""
        with record_job_run("weekly_report", session_factory=sf) as run:
            run.result_summary = {"sent": 1}
        assert self._rows(engine)[0].trigger == "cron"

    def test_args_default_none(self, sf: SessionFactory, engine: Engine) -> None:
        """未传 args -> NULL(非空字典)。"""
        with record_job_run("job_noargs", session_factory=sf):
            pass
        row = self._rows(engine)[0]
        assert row.args is None
        assert row.result_summary is None
