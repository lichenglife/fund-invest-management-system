"""数据中心接口(P1-02a/b，详设§3.2 / §3.2.6 接口设计 / §2.21 契约)。

- GET /api/v1/funds           检索/列表(代码/名称/主题模糊 + 类型 + 分页)
- GET /api/v1/funds/tree      分类树(type/sub_type 聚合计数)
- GET /api/v1/funds/discovery 发现入口(降级, discovery_entries 未建 D2)
- GET /api/v1/fields/{name}   字段解释(降级, field_glossary 未建 D2)
- GET /api/v1/funds/{code}    基金档案(Fund+最新净值+评分)
- GET /api/v1/funds/{code}/nav         净值序列(unit/acc/adj)
- GET /api/v1/funds/{code}/intraday    盘中估算(降级为最新净值, §3.2.7)
- GET /api/v1/funds/{code}/download    净值下载(CSV, 文件头含 source+as_of)
- GET /api/v1/funds/{code}/holdings    前十大持仓
- GET /api/v1/funds/{code}/manager     经理风格箱(降级 50301, managers 未建 D2)

响应统一信封(§2.21)；基金不存在 -> 40002(§4.2)。
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from api.deps import get_db
from api.services.data import DataService
from schemas.envelope import SOURCE_BATCH, SOURCE_CACHE, SOURCE_REALTIME, Envelope
from schemas.errors import ExternalError, NotFoundError

router = APIRouter(tags=["data"])

#: 内置字段词典(field_glossary 表未建, D2 降级用)。
_FIELD_GLOSSARY: dict[str, str] = {
    "code": "基金代码，带交易所后缀(如 000001.OF / 510300.SH)",
    "name": "基金简称",
    "type": "基金类型(stock 混合 / bond 债券 / index 指数 / etf / qdii / money)",
    "sub_type": "子类型(如 偏股混合 / 宽基ETF)",
    "theme": "投资主题(如 消费 / 科技 / 宽基)",
    "style": "风格标签(如 大盘成长 / 中盘价值)",
    "nav": "单位净值",
    "acc_nav": "累计净值(含分红累积)",
    "adj_nav": "后复权净值(分红再投调整, E3 红线口径)",
    "score": "五因子综合评分(0-100, ADR-002 唯一权威源)",
    "composite": "综合评分同 score",
    "max_drawdown": "最大回撤(负值, E5)",
    "sharpe": "年化夏普比率",
}


@router.get("/funds", summary="基金检索/列表(§3.2.2)")
def list_funds(
    db: Annotated[Session, Depends(get_db)],
    q: str | None = Query(default=None, description="代码/名称/主题模糊匹配"),
    type: str | None = Query(default=None, description="基金类型(mixed/stock/bond/...)"),
    page: int = Query(default=1, ge=1, description="页码(从1)"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页大小"),
) -> Envelope[dict[str, Any]]:
    """基金检索/列表(§3.2.2 / §2.21.1 分页)。评分只读批算结果(ADR-002)。"""
    svc = DataService(db)
    data = svc.search_funds(q=q, fund_type=type, page=page, page_size=page_size)
    return Envelope.ok(data=data, source=SOURCE_BATCH, as_of=date.today())


@router.get("/funds/tree", summary="分类树(§3.2.2)")
def fund_tree(
    db: Annotated[Session, Depends(get_db)],
) -> Envelope[dict[str, Any]]:
    """分类树：按 type/sub_type 聚合计数(§3.2.2)。"""
    svc = DataService(db)
    data = svc.fund_tree()
    return Envelope.ok(data=data, source=SOURCE_BATCH, as_of=date.today())


@router.get("/funds/discovery", summary="发现入口(§3.2.2, 降级)")
def discovery(
    db: Annotated[Session, Depends(get_db)],
) -> Envelope[dict[str, Any]]:
    """发现入口(signal/ranking/learn 推荐)。

    discovery_entries 表未建(DEFERRED D2) -> 降级返回空(§2.15 不阻塞)。
    """
    svc = DataService(db)
    data = svc.discovery()
    return Envelope.ok(data=data, source=SOURCE_REALTIME, as_of=date.today())


@router.get("/fields/{name}", summary="字段解释(§3.2.2, 降级)")
def field_glossary(name: str) -> Envelope[dict[str, Any]]:
    """字段解释(field_glossary 表未建 D2 -> 内置词典降级)。

    缓存(§2.8)：fund:glossary:{field} TTL 1h。未知字段返 50301(数据源未就绪)。
    """
    from infra.redis.cache import cache_get, cache_set

    cached = cache_get("glossary", field=name)
    if cached is not None:
        return Envelope.ok(data=cached, source=SOURCE_CACHE, as_of=date.today())

    desc = _FIELD_GLOSSARY.get(name)
    if desc is None:
        raise ExternalError(
            f"字段「{name}」词典未配置(field_glossary 表待落地, D2)",
            code=None,  # 默认 50301
        )
    data = {"field": name, "description": desc}
    cache_set("glossary", field=name, value=data)
    return Envelope.ok(data=data, source=SOURCE_BATCH, as_of=date.today())


@router.get("/funds/{code}", summary="基金档案(§3.2.2)")
def get_fund(
    code: str,
    db: Annotated[Session, Depends(get_db)],
) -> Envelope[dict[str, Any]]:
    """基金档案(Fund + 最新净值 + 评分；缺失字段降级 None, §3.2.2)。"""
    svc = DataService(db)
    profile = svc.get_fund_profile(code)
    if profile is None:
        raise NotFoundError(f"基金不存在: {code}")
    return Envelope.ok(data=profile, source=SOURCE_BATCH, as_of=date.today())


@router.get("/funds/{code}/nav", summary="净值序列(§3.2.2)")
def get_nav(
    code: str,
    db: Annotated[Session, Depends(get_db)],
    days: int = Query(default=252, ge=1, le=5000, description="返回最近 N 个交易日"),
) -> Envelope[list[dict[str, Any]]]:
    """净值序列(unit/acc/adj 三列 + is_estimate)。"""
    svc = DataService(db)
    series = svc.get_nav_series(code, days=days)
    if series is None:
        raise NotFoundError(f"基金不存在: {code}")
    return Envelope.ok(data=series, source=SOURCE_BATCH, as_of=date.today())


@router.get("/funds/{code}/intraday", summary="盘中估算(§3.2.2, 降级)")
def get_intraday(
    code: str,
    db: Annotated[Session, Depends(get_db)],
) -> Envelope[dict[str, Any]]:
    """盘中估算(盘中表未建 -> 降级为最新净值, is_estimate=True, §3.2.7)。"""
    svc = DataService(db)
    data = svc.get_intraday(code)
    if data is None:
        raise NotFoundError(f"基金不存在: {code}")
    return Envelope.ok(data=data, source=SOURCE_REALTIME, as_of=date.today())


@router.get("/funds/{code}/holdings", summary="前十大持仓(§3.2.2)")
def get_holdings(
    code: str,
    db: Annotated[Session, Depends(get_db)],
) -> Envelope[list[dict[str, Any]]]:
    """前十大持仓 + 行业分布(§3.2.2)。"""
    svc = DataService(db)
    holdings = svc.get_holdings(code)
    if holdings is None:
        raise NotFoundError(f"基金不存在: {code}")
    return Envelope.ok(data=holdings, source=SOURCE_BATCH, as_of=date.today())


@router.get("/funds/{code}/manager", summary="经理风格箱(§3.2.2, 降级)")
def get_manager(
    code: str,
    db: Annotated[Session, Depends(get_db)],
) -> Envelope[dict[str, Any]]:
    """经理风格箱(managers 表未建 DEFERRED D2 -> 50301, §2.15)。"""
    from infra.db.models import Fund

    svc = DataService(db)
    result = svc.get_manager(code)
    if result is None and db.get(Fund, code) is None:
        raise NotFoundError(f"基金不存在: {code}")
    raise ExternalError(
        "经理风格箱(managers 表)待落地(DEFERRED D2)", code=None  # 默认 50301
    )


@router.get("/funds/{code}/download", summary="净值下载(§3.2.7)")
def download_nav(
    code: str,
    db: Annotated[Session, Depends(get_db)],
    days: int = Query(default=252, ge=1, le=5000, description="下载最近 N 个交易日"),
) -> Response:
    """净值下载(CSV；文件头含数据源与截至日期, §3.2.7)。

    非 JSON 信封：直接返回 CSV 文件响应。
    """
    svc = DataService(db)
    series = svc.get_nav_series(code, days=days)
    if series is None:
        raise NotFoundError(f"基金不存在: {code}")

    as_of = date.today().isoformat()
    lines = [f"# source=FundLens(AkShare) as_of={as_of} code={code}", "date,nav,acc_nav,adj_nav"]
    for r in series:
        lines.append(
            f"{r['date']},{r['nav']},{r['acc_nav'] if r['acc_nav'] is not None else ''},{r['adj_nav']}"
        )
    csv = "\n".join(lines) + "\n"
    return Response(
        content=csv,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="nav_{code}.csv"'},
    )


__all__: list[str] = ["router"]
