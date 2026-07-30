"""筛选器接口(P1-06a，详设§3.4.6 / §2.21.2 POST /api/screen)。

- POST /api/v1/screen：表单实时筛选(条件+排序+分页,§3.4.6)
- GET /api/v1/screen/dedup：相似去重(占位,P1-06c)

响应统一信封(§2.21)。
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from api.deps import get_db
from domain.screen import ScreenRequest, real_time_screen
from schemas.envelope import SOURCE_BATCH, SOURCE_REALTIME, Envelope

router = APIRouter(tags=["screen"])


class FilterItem(BaseModel):
    """单个筛选条件(§2.21.2 filters)。"""

    model_config = ConfigDict(extra="forbid")

    field: str = Field(description="字段(type/name/score/...)")
    op: str = Field(description="操作符(=,!=,>,>=,<,<=,in,like)")
    value: Any = Field(description="值")


class ScreenPayload(BaseModel):
    """POST /api/screen 请求(§2.21.2)。"""

    model_config = ConfigDict(extra="forbid")

    filters: list[FilterItem] = Field(default_factory=list, description="条件列表(AND)")
    sort: str = Field(default="composite", description="排序字段")
    order: str = Field(default="desc", description="asc/desc")
    page: int = Field(default=1, ge=1, description="页码(从1)")
    page_size: int = Field(default=20, ge=1, le=100, description="每页大小")


@router.post("/screen", summary="表单实时筛选(§3.4.6)")
def screen(
    payload: ScreenPayload,
    db: Annotated[Session, Depends(get_db)],
) -> Envelope[dict[str, Any]]:
    """表单实时筛选(向量化 SQL 过滤 + 排序 + 分页, DC-004)。

    评分排行复用批算结果(scores, ADR-002 唯一权威源)。
    """
    req = ScreenRequest(
        filters=[f.model_dump() for f in payload.filters],
        sort=payload.sort,
        order=payload.order,
        page=payload.page,
        page_size=payload.page_size,
    )
    result = real_time_screen(db, req)
    data = result.to_dict()
    data["as_of"] = date.today().isoformat()
    return Envelope.ok(data=data, source=SOURCE_BATCH, as_of=date.today())


@router.get("/screen/dedup", summary="相似去重(占位, P1-06c)")
def screen_dedup(
    db: Annotated[Session, Depends(get_db)],
    codes: str = "000001,000002",
) -> Envelope[dict[str, Any]]:
    """相似去重(重叠>=70% 提示, P1-06c 待实现)。"""
    _ = db
    code_list = [c.strip() for c in codes.split(",") if c.strip()]
    data: dict[str, Any] = {
        "codes": code_list,
        "available": False,
        "note": "相似去重算法待实现(P1-06c)",
    }
    return Envelope.ok(data=data, source=SOURCE_REALTIME, as_of=date.today())


__all__: list[str] = ["router"]
