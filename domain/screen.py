"""智能筛选器(P1-06a，详设§3.4 / DC-004 / 技术规格 screen.py)。

表单实时过滤：条件组合(filters field/op/value)+ 排序 + 分页。
向量化 SQL 过滤(§3.4.2 SQL/pandas 实时过滤)；结果可缓存 ``screen:{hash}``(§3.4.5)。

> P1-06a 仅表单筛选；NL 解析(P1-06b)、相似去重(P1-06c)随后。
> 评分排行复用批算结果(scores 表,ADR-002 唯一权威源)。
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from infra.db.models import Fund, Score

logger = logging.getLogger(__name__)

#: 筛选结果缓存 TTL(§3.4.5)。
SCREEN_CACHE_TTL = 300  # 5 min

#: 支持的过滤操作符(§2.21.2 filters.op)。
SUPPORTED_OPS = {"=", "!=", ">", ">=", "<", "<=", "in", "not_in", "like"}

#: Fund 表可过滤字段白名单(§3.2 字段，防注入)。映射 field->ORM 属性(type 列属性为 type_)。
FUND_FIELDS = {"code", "name", "type", "sub_type", "theme", "style"}
_FUND_ATTR: dict[str, str] = {"type": "type_"}  # field -> ORM 属性名(其余同名)

#: Score 表可过滤字段(关联 scores 表)。
SCORE_FIELDS = {"score", "composite"}


@dataclass(frozen=True)
class ScreenRequest:
    """筛选请求(§2.21.2 POST /api/screen)。

    Attributes:
        filters: 条件列表 [{field, op, value}]。
        sort: 排序字段(composite/name/type/score)。
        order: asc/desc。
        page: 页码(从1)。
        page_size: 每页大小。
    """

    filters: list[dict[str, Any]] = field(default_factory=list)
    sort: str = "composite"
    order: str = "desc"
    page: int = 1
    page_size: int = 20

    def cache_key(self) -> str:
        """缓存键(§3.4.5 screen:{hash})。"""
        payload = json.dumps(
            {
                "filters": self.filters,
                "sort": self.sort,
                "order": self.order,
                "page": self.page,
                "page_size": self.page_size,
            },
            sort_keys=True,
            default=str,
        )
        return f"screen:{hashlib.md5(payload.encode()).hexdigest()}"


@dataclass(frozen=True)
class ScreenResult:
    """筛选结果(§2.21.2 {items, total})。"""

    items: list[dict[str, Any]] = field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20

    def to_dict(self) -> dict[str, Any]:
        return {
            "items": self.items,
            "total": self.total,
            "page": self.page,
            "page_size": self.page_size,
        }


def real_time_screen(db: Session, req: ScreenRequest) -> ScreenResult:
    """表单实时筛选(§3.4.2 / §3.4.6)。

    向量化 SQL 过滤；funds LEFT JOIN scores(评分可能未算,§3.3.9 批算后填充)。
    排序默认 composite desc；分页 page/page_size。

    Args:
        db: DB session。
        req: 筛选请求。
    Returns:
        ScreenResult(items 含 code/name/type/score)。
    """
    # 构建 funds LEFT JOIN scores 查询(type 列属性为 type_，label 回 type 便于访问)
    stmt = select(Fund.code, Fund.name, Fund.type_.label("type"), Score.composite).outerjoin(
        Score, Fund.code == Score.code
    )

    # 应用过滤
    conditions = []
    for f in req.filters:
        field = f.get("field", "")
        op = f.get("op", "=")
        value = f.get("value")
        if op not in SUPPORTED_OPS:
            continue
        cond = _build_condition(field, op, value)
        if cond is not None:
            conditions.append(cond)

    if conditions:
        stmt = stmt.where(and_(*conditions))

    # 排序(白名单防注入)
    sort_col = _sort_column(req.sort)
    if req.order.lower() == "asc":
        stmt = stmt.order_by(sort_col.asc())
    else:
        stmt = stmt.order_by(sort_col.desc())

    # 分页
    offset = (req.page - 1) * req.page_size if req.page > 0 else 0
    stmt = stmt.offset(offset).limit(req.page_size)

    # 执行
    rows = db.execute(stmt).all()
    items = [
        {
            "code": r.code,
            "name": r.name,
            "type": r.type,
            "score": float(r.composite) if r.composite is not None else None,
        }
        for r in rows
    ]

    # 总数(单独 count 查询，去掉排序/分页)
    count_stmt = select(Fund.code).outerjoin(Score, Fund.code == Score.code)
    if conditions:
        count_stmt = count_stmt.where(and_(*conditions))
    total = len(db.execute(count_stmt).all())

    return ScreenResult(items=items, total=total, page=req.page, page_size=req.page_size)


def _build_condition(field: str, op: str, value: Any) -> Any:
    """构造单条件(SQLAlchemy 表达式,白名单防注入)。"""
    if field in FUND_FIELDS:
        col = getattr(Fund, _FUND_ATTR.get(field, field))
    elif field in SCORE_FIELDS:
        col = Score.composite
    else:
        return None  # 非白名单字段跳过(防注入)

    if op == "=":
        return col == value
    if op == "!=":
        return col != value
    if op == ">":
        return col > value
    if op == ">=":
        return col >= value
    if op == "<":
        return col < value
    if op == "<=":
        return col <= value
    if op == "in" and isinstance(value, list):
        return col.in_(value)
    if op == "not_in" and isinstance(value, list):
        return ~col.in_(value)  # NOT IN(E6 排除 index/etf 用)
    if op == "like" and isinstance(value, str):
        return col.like(value)
    return None


def _sort_column(field: str) -> Any:
    """排序字段(白名单防注入,默认 composite)。"""
    if field in FUND_FIELDS:
        return getattr(Fund, _FUND_ATTR.get(field, field))
    if field in SCORE_FIELDS:
        return Score.composite
    return Fund.code  # 默认


# ---------------------------------------------------------------------------
# 相似去重(P1-06c，§3.4.7 / 技术规格 similarity_dedup)
# ---------------------------------------------------------------------------

#: 去重阈值(§3.4.7)。
SIMILARITY_OVERLAP = 0.70  # 前十大重叠
SIMILARITY_CORR = 0.90  # 收益相关性


@dataclass(frozen=True)
class DedupPair:
    """单对去重结果。"""

    code_a: str
    code_b: str
    overlap: float
    is_similar: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "code_a": self.code_a,
            "code_b": self.code_b,
            "overlap": self.overlap,
            "is_similar": self.is_similar,
        }


@dataclass(frozen=True)
class DedupResult:
    """去重结果(§3.4.7 / 技术规格 DedupResult)。"""

    pairs: list[DedupPair] = field(default_factory=list)
    similar_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "pairs": [p.to_dict() for p in self.pairs],
            "similar_count": self.similar_count,
            "overlap_threshold": SIMILARITY_OVERLAP,
        }


def similarity_dedup(
    holdings_map: dict[str, list[dict[str, Any]]],
    *,
    overlap_threshold: float = SIMILARITY_OVERLAP,
) -> DedupResult:
    """持仓相似去重(§3.4.7 / DC-004)。

    前十大重叠 Jaccard(交集/并集)；超阈值(0.70)提示"高度雷同"。

    Args:
        holdings_map: {code: [{stock_code, weight}]} 前十大持仓。
        overlap_threshold: 重叠阈值(默认 0.70)。
    Returns:
        DedupResult(pairs 含重叠率与 is_similar 标记)。
    """
    codes = list(holdings_map.keys())
    if len(codes) < 2:
        return DedupResult()

    # 各基金前十大股票集合
    stock_sets: dict[str, set[str]] = {
        code: {h["stock_code"] for h in holdings if h.get("stock_code")}
        for code, holdings in holdings_map.items()
    }

    pairs: list[DedupPair] = []
    similar_count = 0
    for i, a in enumerate(codes):
        for b in codes[i + 1 :]:
            set_a, set_b = stock_sets[a], stock_sets[b]
            union = set_a | set_b
            overlap = len(set_a & set_b) / len(union) if union else 0.0  # Jaccard
            is_sim = overlap >= overlap_threshold
            pairs.append(DedupPair(a, b, overlap, is_sim))
            if is_sim:
                similar_count += 1

    return DedupResult(pairs=pairs, similar_count=similar_count)


__all__: list[str] = [
    "SCREEN_CACHE_TTL",
    "SUPPORTED_OPS",
    "ScreenRequest",
    "ScreenResult",
    "SIMILARITY_OVERLAP",
    "SIMILARITY_CORR",
    "DedupPair",
    "DedupResult",
    "similarity_dedup",
    "real_time_screen",
]
