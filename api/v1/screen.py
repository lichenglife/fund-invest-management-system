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


@router.get("/screen/dedup", summary="相似去重(§3.4.7, 重叠>=70%)")
def screen_dedup(
    db: Annotated[Session, Depends(get_db)],
    codes: str = "000001,000002",
) -> Envelope[dict[str, Any]]:
    """持仓相似去重(前十大重叠 Jaccard>=0.70 提示高度雷同, §3.4.7 / DC-004)。"""
    from domain.screen import similarity_dedup

    code_list = [c.strip() for c in codes.split(",") if c.strip()]
    # 从 DB 读各基金最新持仓
    holdings_map: dict[str, list[dict[str, Any]]] = {}
    for code in code_list:
        holdings_map[code] = _load_holdings(db, code)
    result = similarity_dedup(holdings_map)
    data = result.to_dict()
    data["codes"] = code_list
    data["available"] = any(holdings_map.values())
    return Envelope.ok(data=data, source=SOURCE_BATCH, as_of=date.today())


def _load_holdings(db: Session, code: str) -> list[dict[str, Any]]:
    """从 DB 读最新一期持仓(前十大,复用 EvaluationService 逻辑)。"""
    from sqlalchemy import select

    from infra.db.models import Holding

    row = db.execute(
        select(Holding.report_date)
        .where(Holding.code == code)
        .order_by(Holding.report_date.desc())
        .limit(1)
    ).first()
    if row is None:
        return []
    rows = db.execute(
        select(Holding.stock_code, Holding.weight).where(
            Holding.code == code, Holding.report_date == row.report_date
        )
    ).all()
    return [
        {"stock_code": r.stock_code, "weight": float(r.weight) if r.weight else 0.0} for r in rows
    ]


class NLParsePayload(BaseModel):
    """POST /api/screen/nl 请求(§2.21.2)。"""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(description="自然语言查询")
    context: dict[str, Any] | None = Field(default=None, description="上下文(account_id 等)")


@router.post("/screen/nl", summary="NL 解析(规则+LLM+澄清, §3.4.7, E6)")
async def screen_nl(
    payload: NLParsePayload,
) -> Envelope[dict[str, Any]]:
    """自然语言解析 -> 结构化条件或反问(§3.4.7 / DC-004 / E6 红线)。

    生产解析器 = 规则兜底 + LLM 语义解析 + 歧义反问(TP-02 / 提示词稿§6)：
    - ``LLM_API_KEY`` 注入 -> 走 ``nl_parse_with_llm``(规则 fast-path + LLM + normalize)；
    - 无 key -> 规则兜底层(同步)，不阻塞主流程(§2.15 降级)。
    E6：稳健/低风险 -> type∈[bond,mixed](§4 红线，禁止回退)。
    """
    from config.settings import get_settings
    from domain.nl_parse import nl_parse, nl_parse_with_llm

    if get_settings().llm_api_key:
        result = await nl_parse_with_llm(payload.query, context=payload.context)
    else:
        result = nl_parse(payload.query, context=payload.context)
    return Envelope.ok(data=result.to_dict(), source=SOURCE_REALTIME, as_of=date.today())


__all__: list[str] = ["router"]
