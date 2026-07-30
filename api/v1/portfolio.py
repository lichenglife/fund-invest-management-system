"""组合配置接口(P1-08a，详设§3.6.5 / DC-006)。

- POST /api/v1/portfolios：创建组合
- POST /api/v1/portfolios/import：从模拟持仓导入
- GET /api/v1/portfolios：列出组合
- GET /api/v1/portfolios/{id}：查组合详情
- DELETE /api/v1/portfolios/{id}：删除组合
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from api.deps import get_db
from api.services.portfolio import PortfolioService
from schemas.envelope import SOURCE_REALTIME, Envelope
from schemas.portfolio import ImportFromPaperRequest, PortfolioCreateRequest

router = APIRouter(prefix="/portfolios", tags=["portfolio"])


@router.post("", summary="创建组合(§3.6.5)")
def create_portfolio(
    req: PortfolioCreateRequest,
    db: Annotated[Session, Depends(get_db)],
) -> Envelope[dict[str, Any]]:
    """创建组合：手动/模板 + 权重(§3.6.2)。"""
    svc = PortfolioService(db)
    result = svc.create(
        account_id=req.account_id,
        name=req.name,
        source=req.source,
        weights=[w.model_dump() for w in req.weights],
    )
    return Envelope.ok(data=result, source=SOURCE_REALTIME, as_of=date.today())


@router.post("/import", summary="从模拟持仓导入(§3.6.1)")
def import_from_paper(
    req: ImportFromPaperRequest,
    db: Annotated[Session, Depends(get_db)],
) -> Envelope[dict[str, Any]]:
    """从模拟持仓一键导入组合(§3.6.1)。"""
    svc = PortfolioService(db)
    result = svc.create_from_paper(account_id=req.account_id, name=req.name)
    return Envelope.ok(data=result, source=SOURCE_REALTIME, as_of=date.today())


@router.get("", summary="列出组合")
def list_portfolios(
    db: Annotated[Session, Depends(get_db)],
    account_id: str = Query(default="default", description="账户 ID"),
) -> Envelope[list[dict[str, Any]]]:
    """列出账户下所有组合。"""
    svc = PortfolioService(db)
    result = svc.list_portfolios(account_id)
    return Envelope.ok(data=result, source=SOURCE_REALTIME, as_of=date.today())


@router.get("/{portfolio_id}", summary="查组合详情(§3.6.5)")
def get_portfolio(
    portfolio_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> Envelope[dict[str, Any]]:
    """查组合详情(含权重)。"""
    svc = PortfolioService(db)
    result = svc.get(portfolio_id)
    return Envelope.ok(data=result, source=SOURCE_REALTIME, as_of=date.today())


@router.delete("/{portfolio_id}", summary="删除组合")
def delete_portfolio(
    portfolio_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> Envelope[dict[str, Any]]:
    """删除组合(级联删权重)。"""
    svc = PortfolioService(db)
    result = svc.delete(portfolio_id)
    return Envelope.ok(data=result, source=SOURCE_REALTIME, as_of=date.today())


__all__: list[str] = ["router"]
