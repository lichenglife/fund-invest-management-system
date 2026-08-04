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

import pandas as pd
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.deps import get_db
from api.services.portfolio import PortfolioService
from schemas.envelope import SOURCE_BATCH, SOURCE_REALTIME, Envelope
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


@router.get("/{portfolio_id}/diagnosis", summary="组合诊断红黄绿(§3.6.6.1, TP-03)")
def diagnose_portfolio(
    portfolio_id: str,
    db: Annotated[Session, Depends(get_db)],
    risk_type: str = Query(
        default="moderate", description="风险偏好(conservative/moderate/aggressive)"
    ),
) -> Envelope[dict[str, Any]]:
    """组合诊断：五维红黄绿 + 整体评级 + 再平衡(E8/E9/E12)。"""
    from domain.diagnosis import diagnose
    from infra.db.models import Fund

    svc = PortfolioService(db)
    portfolio = svc.get(portfolio_id)  # 40002 if not found
    weights = {w["code"]: w["weight"] for w in portfolio["weights"]}

    # 查基金类型
    codes = list(weights.keys())
    funds = (
        db.execute(select(Fund.code, Fund.type_).where(Fund.code.in_(codes))).all() if codes else []
    )
    fund_types = {f.code: f.type_ for f in funds}

    report = diagnose(portfolio_id, weights, fund_types=fund_types, risk_type=risk_type)
    return Envelope.ok(data=report.to_dict(), source=SOURCE_REALTIME, as_of=date.today())


@router.get("/{portfolio_id}/backtest", summary="组合回测(§3.6.7, TP-04, E3/E14)")
def backtest_portfolio(
    portfolio_id: str,
    db: Annotated[Session, Depends(get_db)],
    window: str = Query(default="3y", description="回测窗口(3y/5y/all)"),
    bench: str | None = Query(default=None, description="基准代码(覆盖自适应,E14)"),
) -> Envelope[dict[str, Any]]:
    """组合回测：vs 自适应全收益基准(E14)；后复权净值(E3)；严格时序。"""
    from domain.backtest_portfolio import pick_benchmark, portfolio_backtest
    from infra.db.models import Fund

    svc = PortfolioService(db)
    portfolio = svc.get(portfolio_id)  # 40002 if not found
    weights = {w["code"]: w["weight"] for w in portfolio["weights"]}
    if not weights:
        return Envelope.ok(
            data={"available": False, "note": "组合无持仓"},
            source=SOURCE_BATCH,
            as_of=date.today(),
        )
    # 权重和>1.05 拒绝(§5)
    if sum(weights.values()) > 1.05:
        from schemas.errors import ParamError

        raise ParamError("组合权重和超过 1.05，请先校准")

    codes = list(weights.keys())
    funds = (
        db.execute(select(Fund.code, Fund.type_).where(Fund.code.in_(codes))).all() if codes else []
    )
    fund_types = {f.code: f.type_ for f in funds}

    start = _window_start(window)
    # 各成分后复权净值(E3)
    nav_dict: dict[str, pd.Series] = {}
    for code in codes:
        nav = _load_adj_nav(db, code, start)
        if nav is not None:
            nav_dict[code] = nav

    # 基准(E14：自适应全收益指数，用户可覆盖)
    bench_code = bench or pick_benchmark(weights, fund_types)
    bench_nav = _load_adj_nav(db, bench_code, start)

    result = portfolio_backtest(nav_dict, weights, bench_nav=bench_nav, bench_code=bench_code)
    data = result.to_dict()
    data["portfolio_id"] = portfolio_id
    if not nav_dict:
        data["available"] = False
        data["note"] = "净值数据不足"
    return Envelope.ok(data=data, source=SOURCE_BATCH, as_of=date.today())


@router.get("/{portfolio_id}/rebalance", summary="再平衡提醒(§3.6.5, FR-24/37, E8)")
def rebalance_portfolio(
    portfolio_id: str,
    db: Annotated[Session, Depends(get_db)],
    risk_type: str = Query(default="moderate", description="风险偏好"),
) -> Envelope[dict[str, Any]]:
    """再平衡阈值检查：偏离目标>5% 触发(E8，§3.6.5 / TP-03 §5)。"""
    from domain.diagnosis import diagnose
    from infra.db.models import Fund

    svc = PortfolioService(db)
    portfolio = svc.get(portfolio_id)  # 40002 if not found
    weights = {w["code"]: w["weight"] for w in portfolio["weights"]}

    codes = list(weights.keys())
    funds = (
        db.execute(select(Fund.code, Fund.type_).where(Fund.code.in_(codes))).all() if codes else []
    )
    fund_types = {f.code: f.type_ for f in funds}

    # 复用诊断的再平衡逻辑(TP-03 §5)
    report = diagnose(portfolio_id, weights, fund_types=fund_types, risk_type=risk_type)
    return Envelope.ok(
        data={
            "portfolio_id": portfolio_id,
            "rating": report.rating,
            "rebalance": report.rebalance,
            "asset_dim": report.per_dim["asset"],
        },
        source=SOURCE_REALTIME,
        as_of=date.today(),
    )


def _window_start(window: str) -> date:
    """窗口 -> 起始日期。"""
    today = date.today()
    if window == "5y":
        return today.replace(year=today.year - 5)
    if window == "all":
        return date(2010, 1, 1)
    return today.replace(year=today.year - 3)  # 默认 3y


def _load_adj_nav(db: Session, code: str, start: date) -> pd.Series | None:
    """从 DB 读后复权净值序列(adj_nav，E3)。"""
    from infra.db.models import Nav

    rows = db.execute(
        select(Nav.trade_date, Nav.adj_nav)
        .where(Nav.code == code, Nav.trade_date >= start)
        .order_by(Nav.trade_date)
    ).all()
    if not rows:
        return None
    dates = [r.trade_date for r in rows]
    values = [float(r.adj_nav) for r in rows if r.adj_nav is not None]
    return pd.Series(values, index=pd.to_datetime(dates)) if values else None


__all__: list[str] = ["router"]
