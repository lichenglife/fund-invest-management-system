"""评估引擎接口(P1-04a/b，详设§3.3.6 / §2.21 信封 / §3.3.7 溯源)。

- GET /api/v1/funds/{code}/metrics：核心指标(cv_flag 交叉验证)
- GET /api/v1/funds/{code}/score：五因子评分(可调权重, ADR-002 唯一权威源)
- GET /api/v1/funds/{code}/stylebox：风格箱(E13 权益类)
- GET /api/v1/funds/{code}/attribution：Brinson 归因(仅 mixed/stock, §3.3.8.2)
- GET /api/v1/funds/{code}/research：研究指标卡片(PEG/ERP 代理, §3.3.7)

响应统一信封(§2.21)；数值带 source + as_of + cv_flag(§3.3.7)。
基金不存在 -> 40002(§4.2)。
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from api.deps import get_db
from api.services.evaluation import EvaluationService
from domain.research import research_metrics_cards
from schemas.envelope import SOURCE_BATCH, SOURCE_REALTIME, Envelope
from schemas.errors import NotFoundError

router = APIRouter(tags=["evaluation"])


@router.get("/funds/{code}/metrics", summary="基金核心指标(§3.3.2)")
def get_metrics(
    code: str,
    db: Annotated[Session, Depends(get_db)],
    window: str = Query(default="3Y", description="评估窗口(3Y/1Y/5Y)"),
    benchmark: str = Query(default="auto", description="基准(auto=按类型自动选)"),
) -> Envelope[dict[str, Any]]:
    """核心指标(年化/夏普/卡玛/索提诺/最大回撤 + cv_flag 交叉验证，§3.3.7)。"""
    svc = EvaluationService(db)
    metrics = svc.get_metrics(code, window=window, benchmark=benchmark)
    if metrics is None:
        raise NotFoundError(f"基金不存在: {code}")
    data = metrics.to_dict()
    # 溯源(§3.3.7)：source + as_of + cv_flag
    data["as_of"] = date.today().isoformat()
    return Envelope.ok(
        data=data,
        source=SOURCE_BATCH,
        as_of=date.today(),
    )


@router.get("/funds/{code}/score", summary="五因子评分(§3.3.8.1, 唯一权威源)")
def get_score(
    code: str,
    db: Annotated[Session, Depends(get_db)],
    weights: str | None = Query(
        default=None, description="可调权重(ret:risk:perf:scale:manager, 如 20:25:20:15:20)"
    ),
) -> Envelope[dict[str, Any]]:
    """五因子综合评分(可调权重, ADR-002 唯一权威源)。"""
    svc = EvaluationService(db)
    custom_weights = _parse_weights(weights)
    score = svc.get_score(code, weights=custom_weights)
    if score is None:
        raise NotFoundError(f"基金不存在: {code}")
    data: dict[str, Any] = score.to_dict()
    data["as_of"] = date.today().isoformat()
    return Envelope.ok(
        data=data,
        source=SOURCE_BATCH,
        as_of=date.today(),
    )


@router.get("/funds/{code}/stylebox", summary="风格箱(§3.3.1, E13 权益类)")
def get_stylebox(
    code: str,
    db: Annotated[Session, Depends(get_db)],
) -> Envelope[dict[str, Any]]:
    """风格箱(size, value_growth)；仅权益类(闭合 E13)，债/货/QDII 不显示。"""
    svc = EvaluationService(db)
    result = svc.get_stylebox(code)
    if result is None:
        raise NotFoundError(f"基金不存在或类型不支持风格箱: {code}")
    size, vg = result
    data: dict[str, Any] = {
        "size": size,
        "value_growth": vg,
        "available": size is not None and vg is not None,
        "note": "风格箱算法待实现(P1-03)" if size is None else None,
    }
    return Envelope.ok(data=data, source=SOURCE_REALTIME, as_of=date.today())


@router.get("/funds/{code}/attribution", summary="Brinson 归因(§3.3.8.2, 仅 mixed/stock)")
def get_attribution(
    code: str,
    db: Annotated[Session, Depends(get_db)],
) -> Envelope[dict[str, Any]]:
    """Brinson 业绩归因(仅主动股混基；指数->TE/IR；债基不显示, §3.3.8.2)。"""
    svc = EvaluationService(db)
    attr = svc.get_attribution(code)
    if attr is None:
        raise NotFoundError(f"基金不存在: {code}")
    data: dict[str, Any] = attr.to_dict()
    data["as_of"] = date.today().isoformat()
    return Envelope.ok(data=data, source=SOURCE_BATCH, as_of=date.today())


@router.get("/funds/{code}/research", summary="研究指标卡片(§3.3.7, PEG/ERP 代理)")
def get_research(
    code: str,
    db: Annotated[Session, Depends(get_db)],
    rf_rate: float = Query(default=0.025, description="10Y 国债收益率(无风险利率)"),
) -> Envelope[dict[str, Any]]:
    """研究指标卡片(PEG/ERP 代理 + 阈值着色, §3.3.7 / 40301 守卫)。"""
    svc = EvaluationService(db)
    peg, erp = svc.get_research(code, rf_rate=rf_rate)
    if not peg.available and peg.method == "fund_missing":
        raise NotFoundError(f"基金不存在: {code}")
    cards = research_metrics_cards(peg, erp)
    data: dict[str, Any] = {
        "peg": peg.to_dict(),
        "erp": erp.to_dict(),
        "cards": [c.to_dict() for c in cards],
    }
    return Envelope.ok(data=data, source=SOURCE_BATCH, as_of=date.today())


def _parse_weights(weights_str: str | None) -> dict[str, int] | None:
    """解析权重查询参数(ret:risk:perf:scale:manager -> dict)。

    格式：``20:25:20:15:20``；非法返回 None(用默认)。
    """
    if not weights_str:
        return None
    parts = weights_str.split(":")
    if len(parts) != 5:
        return None
    try:
        vals = [int(p) for p in parts]
    except ValueError:
        return None
    keys = ["ret", "risk", "perf", "scale", "manager"]
    return dict(zip(keys, vals, strict=True))


__all__: list[str] = ["router"]
