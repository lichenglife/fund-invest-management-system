"""管理鉴权路由(§2.19.6 单用户 MVP)。

- POST /api/v1/admin/login：登录签发 AES 会话令牌(§2.19.6 默认账户 + AES 密码校验)。
- POST /api/v1/admin/change-password：首次登录强制改密。
- GET /api/v1/admin/whoami：受保护端点示例(校验依赖注入层鉴权)。
- POST /api/v1/admin/trigger-job：手动触发采集作业(§3.14.4，须管理员)。
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.auth import get_current_admin
from api.deps import get_db
from config.settings import settings
from domain.collect_service import CollectService
from domain.scheduler import record_job_run
from infra.db.models.admin import AdminUser
from infra.db.models.scheduler import SchedulerJob
from infra.security.crypto import encrypt, verify
from infra.security.token import create_access_token
from schemas.auth import ChangePasswordRequest, LoginData, LoginRequest, WhoAmIData
from schemas.envelope import SOURCE_REALTIME, Envelope
from schemas.errors import AuthError, ErrorCode, ParamError

router = APIRouter(prefix="/admin", tags=["admin"])


class TriggerJobRequest(BaseModel):
    """手动触发作业请求(§3.14.4)。"""

    model_config = ConfigDict(extra="forbid")

    job: str = Field(description="作业名：fund_list / nav / holdings")
    code: str | None = Field(default=None, description="基金代码(nav/holdings 必填)")
    start: str | None = Field(default=None, description="净值起始 YYYYMMDD(nav)")
    end: str | None = Field(default=None, description="净值结束 YYYYMMDD(nav)")
    year: str | None = Field(default=None, description="重仓年份(holdings)")


router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/login", summary="管理员登录")
def login(
    req: LoginRequest,
    db: Annotated[Session, Depends(get_db)],
) -> Envelope[LoginData]:
    """校验用户名+密码(§2.19.6 AES 解密比对)，签发 AES 会话令牌。"""
    user = db.query(AdminUser).filter(AdminUser.username == req.username).first()
    # 用户不存在或密码错误统一返 40101(不区分，防枚举)
    if user is None or not verify(req.password, user.password_encrypted):
        raise AuthError("用户名或密码错误", code=ErrorCode.UNAUTHENTICATED)

    token = create_access_token(user.username)
    return Envelope.ok(
        data=LoginData(
            access_token=token,
            must_change_password=user.must_change_password,
            expires_in_minutes=settings.admin_session_ttl_min,
        ),
        source=SOURCE_REALTIME,
    )


@router.post("/change-password", summary="修改密码(首次登录强制)")
def change_password(
    req: ChangePasswordRequest,
    db: Annotated[Session, Depends(get_db)],
    current: Annotated[AdminUser, Depends(get_current_admin)],
) -> Envelope[dict[str, bool]]:
    """修改密码；校验旧密码、置 must_change_password=False(§2.19.6)。"""
    if not verify(req.old_password, current.password_encrypted):
        raise AuthError("原密码错误", code=ErrorCode.UNAUTHENTICATED)
    current.password_encrypted = encrypt(req.new_password)
    current.must_change_password = False
    db.commit()
    return Envelope.ok(data={"changed": True}, source=SOURCE_REALTIME)


@router.get("/whoami", summary="当前管理员信息(受保护)")
def whoami(
    current: Annotated[AdminUser, Depends(get_current_admin)],
) -> Envelope[WhoAmIData]:
    """受保护端点示例：验证依赖注入层鉴权(§6.4)。"""
    return Envelope.ok(
        data=WhoAmIData(
            username=current.username,
            must_change_password=current.must_change_password,
        ),
        source=SOURCE_REALTIME,
    )


@router.post("/trigger-job", summary="手动触发采集作业(§3.14.4)")
def trigger_job(
    req: TriggerJobRequest,
    db: Annotated[Session, Depends(get_db)],
    current: Annotated[AdminUser, Depends(get_current_admin)],
) -> Envelope[dict[str, int]]:
    """手动触发采集作业(§3.14.4，须管理员 §2.19.6)；执行结果落库 scheduler_jobs(§3.14.3)。

    未登录 40101、非管理员 40103(§3.14.5)；作业幂等(§3.14.6 锁防重)。
    参数校验先于记录，避免坏请求污染执行历史。
    """
    # current 已鉴权(§6.4 依赖层)，此处不再散落判断
    _ = current
    job_names = {"fund_list": "基金名单采集", "nav": "净值采集", "holdings": "重仓采集"}
    if req.job not in job_names:
        raise ParamError(f"未知作业: {req.job}")
    if req.job in ("nav", "holdings") and not req.code:
        raise ParamError(f"{req.job} 作业需指定 code")

    service = CollectService(db)
    args = {"code": req.code, "start": req.start, "end": req.end, "year": req.year}
    with record_job_run(
        f"collect_{req.job}", job_names[req.job], trigger="manual", args=args
    ) as run:
        if req.job == "fund_list":
            count = service.collect_fund_list()
        elif req.job == "nav":
            assert req.code is not None  # 已于 record_job_run 前校验(mypy narrowing)
            count = service.collect_nav(req.code, start=req.start or "", end=req.end or "")
        else:  # holdings
            assert req.code is not None  # 已于 record_job_run 前校验(mypy narrowing)
            count = service.collect_holdings(req.code, req.year or str(date.today().year))
        run.result_summary = {"upserted": count}
    return Envelope.ok(data={"upserted": count}, source=SOURCE_REALTIME)


@router.get("/jobs", summary="定时任务执行历史(§3.14.3 scheduler_jobs)")
def list_jobs(
    db: Annotated[Session, Depends(get_db)],
    current: Annotated[AdminUser, Depends(get_current_admin)],
    limit: int = Query(default=100, ge=1, le=500, description="返回条数上限"),
    days: int = Query(default=7, ge=1, le=90, description="近 N 天"),
) -> Envelope[list[dict[str, Any]]]:
    """定时任务执行历史(每行=一次执行)；按 started_at 倒序(§3.14.3)。

    须管理员(§2.19.6)；未登录 40101。前端后台管理页消费(对齐 mock ADMIN_JOBS)。
    """
    _ = current
    cutoff = datetime.now(UTC) - timedelta(days=days)
    rows = (
        db.execute(
            select(SchedulerJob)
            .where(SchedulerJob.started_at >= cutoff)
            .order_by(SchedulerJob.started_at.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    data = [_job_to_dict(r) for r in rows]
    return Envelope.ok(data=data, source=SOURCE_REALTIME)


def _job_to_dict(row: SchedulerJob) -> dict[str, Any]:
    """scheduler_jobs 行 -> dict(字段对齐前端 mock ADMIN_JOBS)。"""
    return {
        "id": row.id,
        "job_id": row.job_id,
        "job_name": row.job_name,
        "trigger": row.trigger,
        "status": row.status,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "duration_ms": row.duration_ms,
        "error": row.error,
        "args": row.args,
        "result_summary": row.result_summary,
    }
