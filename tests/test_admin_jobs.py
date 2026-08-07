"""GET /api/v1/admin/jobs 定时任务执行历史接口测试(详设§3.14.3 / §3.14.5)。

验证：
- 未带令牌 -> 40101(§2.19.6)。
- 7 字段信封(§2.21)。
- 按 started_at 倒序(§3.14.3)。
- 字段对齐前端 mock ADMIN_JOBS(app/mock/store.py)。
- days 近 N 天过滤、limit 截断。
- 无历史 -> 空列表。

种子 SchedulerJob 直接落库(避免 AkShare 网络)。
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from api.deps import get_db
from infra.db.models import AdminUser
from infra.db.models.scheduler import SchedulerJob
from infra.security import crypto

#: 前端 mock ADMIN_JOBS 约定的字段集(app/mock/store.py)。
JOB_FIELDS = {
    "id",
    "job_id",
    "job_name",
    "trigger",
    "status",
    "started_at",
    "finished_at",
    "duration_ms",
    "error",
    "args",
    "result_summary",
}

ENVELOPE_FIELDS = {"code", "data", "source", "as_of", "disclaimer", "message", "trace_id"}


@pytest.mark.db
class TestAdminJobsAPI:
    """GET /api/v1/admin/jobs(§3.14.3 scheduler_jobs)。"""

    @pytest.fixture()
    def client_with_admin(self, db_session: Session) -> Iterator[TestClient]:
        """种子 admin + 三条 scheduler_jobs 历史 + TestClient(get_db override 指向共享引擎)。"""
        from api.main import create_app

        engine = db_session.bind
        TestSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
        now = datetime.now(UTC)
        with TestSession() as s:
            s.add(
                AdminUser(
                    username="admin",
                    password_encrypted=crypto.encrypt("InitPass123"),
                    must_change_password=True,
                )
            )
            # 三条历史：3 天前 / 12 小时前 / 1 小时前(不同 trigger/status，便于排序/过滤断言)
            s.add_all(
                [
                    SchedulerJob(
                        job_id="collect_all",
                        job_name="增量采集",
                        trigger="cron",
                        status="success",
                        started_at=now - timedelta(days=3),
                        finished_at=now - timedelta(days=3, seconds=-2),
                        duration_ms=2000,
                        args={"codes": []},
                        result_summary={"funds": 5},
                    ),
                    SchedulerJob(
                        job_id="fund_recalc",
                        job_name="指标重算",
                        trigger="cron",
                        status="failed",
                        started_at=now - timedelta(hours=12),
                        finished_at=now - timedelta(hours=12, seconds=-1),
                        duration_ms=1000,
                        error="boom",
                        args={"window": "1Y"},
                    ),
                    SchedulerJob(
                        job_id="collect_nav",
                        job_name="净值采集",
                        trigger="manual",
                        status="success",
                        started_at=now - timedelta(hours=1),
                        finished_at=now - timedelta(hours=1, seconds=-1),
                        duration_ms=500,
                        args={"code": "000001"},
                        result_summary={"upserted": 30},
                    ),
                ]
            )
            s.commit()

        def _override_get_db() -> Iterator[Session]:
            db = TestSession()
            try:
                yield db
            finally:
                db.close()

        app = create_app()
        app.dependency_overrides[get_db] = _override_get_db
        with TestClient(app) as c:
            yield c
        app.dependency_overrides.clear()

    @staticmethod
    def _token(client: TestClient) -> str:
        data = client.post(
            "/api/v1/admin/login", json={"username": "admin", "password": "InitPass123"}
        ).json()["data"]
        token = data["access_token"]
        assert isinstance(token, str)
        return token

    def test_jobs_requires_auth_40101(self, client_with_admin: TestClient) -> None:
        """§2.19.6 /admin/jobs 未带令牌 -> 40101。"""
        resp = client_with_admin.get("/api/v1/admin/jobs")
        assert resp.status_code == 401
        assert resp.json()["code"] == 40101

    def test_jobs_envelope_seven_fields(self, client_with_admin: TestClient) -> None:
        """§2.21 7 字段信封 + 非空列表。"""
        tok = self._token(client_with_admin)
        resp = client_with_admin.get(
            "/api/v1/admin/jobs", headers={"Authorization": f"Bearer {tok}"}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert set(body.keys()) == ENVELOPE_FIELDS
        assert body["code"] == 0
        assert isinstance(body["data"], list)
        assert len(body["data"]) == 3

    def test_jobs_ordered_desc_by_started_at(self, client_with_admin: TestClient) -> None:
        """按 started_at 倒序(§3.14.3)；字段对齐前端 mock ADMIN_JOBS。"""
        tok = self._token(client_with_admin)
        resp = client_with_admin.get(
            "/api/v1/admin/jobs", headers={"Authorization": f"Bearer {tok}"}
        )
        data = resp.json()["data"]
        assert [d["job_id"] for d in data] == ["collect_nav", "fund_recalc", "collect_all"]

        first = data[0]
        assert set(first.keys()) == JOB_FIELDS
        assert first["job_id"] == "collect_nav"
        assert first["job_name"] == "净值采集"
        assert first["trigger"] == "manual"
        assert first["status"] == "success"
        assert first["duration_ms"] == 500
        assert first["error"] is None
        assert first["args"] == {"code": "000001"}
        assert first["result_summary"] == {"upserted": 30}
        assert first["started_at"] is not None
        assert first["finished_at"] is not None

        # failed 行携带 error
        failed = next(d for d in data if d["job_id"] == "fund_recalc")
        assert failed["status"] == "failed"
        assert failed["error"] == "boom"
        assert failed["result_summary"] is None

    def test_jobs_days_filter_excludes_old(self, client_with_admin: TestClient) -> None:
        """days 近 N 天过滤：近 1 天排除 3 天前的 collect_all，保留 12 小时前与 1 小时前的行。"""
        tok = self._token(client_with_admin)
        resp = client_with_admin.get(
            "/api/v1/admin/jobs?days=1",
            headers={"Authorization": f"Bearer {tok}"},
        )
        data = resp.json()["data"]
        ids = {d["job_id"] for d in data}
        assert ids == {"collect_nav", "fund_recalc"}

    def test_jobs_days_7_includes_all(self, client_with_admin: TestClient) -> None:
        """默认/近 7 天含全部三条。"""
        tok = self._token(client_with_admin)
        resp = client_with_admin.get(
            "/api/v1/admin/jobs?days=7",
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert len(resp.json()["data"]) == 3

    def test_jobs_limit_truncates(self, client_with_admin: TestClient) -> None:
        """limit 截断返回条数(取最新 N 条)。"""
        tok = self._token(client_with_admin)
        resp = client_with_admin.get(
            "/api/v1/admin/jobs?limit=2",
            headers={"Authorization": f"Bearer {tok}"},
        )
        data = resp.json()["data"]
        assert len(data) == 2
        assert [d["job_id"] for d in data] == ["collect_nav", "fund_recalc"]

    def test_jobs_empty_when_no_history(self, db_session: Session) -> None:
        """无执行历史 -> 空列表信封。"""
        from api.main import create_app

        engine = db_session.bind
        TestSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
        with TestSession() as s:
            s.add(
                AdminUser(
                    username="admin",
                    password_encrypted=crypto.encrypt("InitPass123"),
                    must_change_password=True,
                )
            )
            s.commit()

        def _override_get_db() -> Iterator[Session]:
            db = TestSession()
            try:
                yield db
            finally:
                db.close()

        app = create_app()
        app.dependency_overrides[get_db] = _override_get_db
        try:
            with TestClient(app) as c:
                tok = self._token(c)
                resp = c.get("/api/v1/admin/jobs", headers={"Authorization": f"Bearer {tok}"})
        finally:
            app.dependency_overrides.clear()
        assert resp.status_code == 200
        body = resp.json()
        assert set(body.keys()) == ENVELOPE_FIELDS
        assert body["data"] == []
