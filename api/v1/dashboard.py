"""仪表盘聚合接口(P1-12，详设§3.13 / DC-001 / FR-D1~D6)。

- GET /api/v1/dashboard  聚合状态/榜单/动态/学一基

Top10 评分来自评估引擎唯一权威源(DC-003，只读 scores 表)；
缓存 fund:dashboard:{account_id}(5min)、fund:top10:{type}(15min)(§3.13.5)。
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from api.deps import get_db
from api.services.dashboard import DEFAULT_ACCOUNT, DashboardService
from schemas.envelope import SOURCE_BATCH, SOURCE_CACHE, Envelope

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard", summary="仪表盘聚合(§3.13, FR-D1~D6)")
def get_dashboard(
    db: Annotated[Session, Depends(get_db)],
    account_id: str = Query(default=DEFAULT_ACCOUNT, description="账户 ID"),
    type: str = Query(default="all", description="Top10 类型(all/stock/mixed/bond/etf/qdii/money)"),
) -> Envelope[dict[str, Any]]:
    """聚合首页四区：状态卡 / Top10 / 近期动态 / 学一基。

    ``type=all`` 跨类型取 Top10；否则按类型过滤(§3.13.2 类型 Tab)。
    命中缓存时 source=cache，否则 source=batch(§3.13.5)。
    """
    from infra.redis.cache import cache_get, cache_set

    cached = cache_get("dashboard", account_id=account_id, type=type)
    if cached is not None:
        return Envelope.ok(data=cached, source=SOURCE_CACHE, as_of=date.today())

    svc = DashboardService(db)
    data = svc.aggregate(account_id=account_id, fund_type=type)
    cache_set("dashboard", account_id=account_id, type=type, value=data)
    return Envelope.ok(data=data, source=SOURCE_BATCH, as_of=date.today())


__all__: list[str] = ["router"]
