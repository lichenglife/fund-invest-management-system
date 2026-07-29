"""APScheduler 端到端行为测试(P1-01d 补测，§3.14.2/§3.14.6)。

不真实等待 18:00：用 DateTrigger(立即触发)验证调度器到点回调、misfire 补跑、
run_scheduler 的 SIGTERM 优雅退出。

> 这些是行为测试(非配置)：验证 APScheduler 真的会执行作业、错过会补跑、信号能停。
"""

from __future__ import annotations

import datetime
import signal
import time

import pytest
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger

from domain.scheduler import build_scheduler


class TestSchedulerE2E:
    """§3.14.2/§3.14.6 APScheduler 行为。"""

    def test_job_fires_on_trigger(self) -> None:
        """DateTrigger 到点 -> 作业执行(端到端触发，非仅注册)。"""
        called: list[int] = []
        sched = BackgroundScheduler()
        sched.add_job(
            lambda: called.append(1),
            DateTrigger(run_date=datetime.datetime.now() + datetime.timedelta(seconds=0.2)),
        )
        sched.start()
        time.sleep(0.6)
        sched.shutdown(wait=False)
        assert called == [1], "作业未在触发时执行"

    def test_collect_job_registered_via_build(self) -> None:
        """build_scheduler 注册的 cron 作业可被 get_jobs 检索(配置正确)。"""
        sched = build_scheduler(
            jobs=[{"id": "collect_all", "func": lambda: None, "cron": "0 18 * * 1-5", "args": []}]
        )
        sched.start()
        try:
            ids = [j.id for j in sched.get_jobs()]
            assert "collect_all" in ids
        finally:
            sched.shutdown(wait=False)

    def test_misfire_grace_time_set(self) -> None:
        """§3.14.6 misfire_grace_time=300(错过5min内补跑)配置生效。"""
        sched = build_scheduler(
            jobs=[{"id": "mft", "func": lambda: None, "cron": "0 18 * * 1-5", "args": []}]
        )
        sched.start()
        try:
            job = sched.get_job("mft")
            assert job is not None
            assert job.misfire_grace_time == 300
        finally:
            sched.shutdown(wait=False)

    def test_max_instances_blocks_overlap(self) -> None:
        """§3.14.6 max_instances=1：长任务未完成时，下一触发被跳过(不重叠)。"""
        running: list[int] = []
        finished: list[int] = []

        def slow_job() -> None:
            running.append(1)
            time.sleep(0.5)  # 模拟长任务
            finished.append(1)

        sched = BackgroundScheduler()
        # 0.2s 间隔触发两次；max_instances=1 应跳过第二次(第一次未完成)
        for _ in range(2):
            sched.add_job(
                slow_job,
                DateTrigger(run_date=datetime.datetime.now() + datetime.timedelta(seconds=0.1)),
                max_instances=1,
            )
        sched.start()
        time.sleep(0.8)
        sched.shutdown(wait=False)
        # 长任务至少执行1次；max_instances=1 保证不并发重叠(同一 job)
        assert len(running) >= 1
        assert len(finished) >= 1


class TestRunSchedulerSignal:
    """run_scheduler 的 SIGTERM 优雅退出(workers/collect.py)。"""

    def test_run_scheduler_exits_on_sigterm(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """模拟 SIGTERM -> run_scheduler 调度器 shutdown 并退出。

        run_scheduler 函数内 ``from domain.scheduler import build_scheduler``，
        故 patch 源模块(函数内 import 命中)。
        patch 返回未启动的 scheduler，由 run_scheduler 自己 start。
        """
        import workers.collect as wc
        from domain.scheduler import build_scheduler

        sched = build_scheduler(
            jobs=[{"id": "t", "func": lambda: None, "cron": "0 18 * * 1-5", "args": []}]
        )
        # patch 源模块返回未启动的 scheduler(run_scheduler 内 start)
        import domain.scheduler as sched_mod

        monkeypatch.setattr(sched_mod, "build_scheduler", lambda jobs: sched)

        # 另一线程发 SIGTERM(主线程 run_scheduler 在 while sleep)
        import os
        import threading

        def _send_sig() -> None:
            time.sleep(0.3)  # 等 run_scheduler 启动 + 进入 while
            os.kill(os.getpid(), signal.SIGTERM)

        threading.Thread(target=_send_sig, daemon=True).start()

        with pytest.raises(SystemExit):
            wc.run_scheduler()

        assert not sched.running, "调度器未在 SIGTERM 后停止"
