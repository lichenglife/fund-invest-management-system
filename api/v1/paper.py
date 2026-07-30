"""模拟交易接口(P1-07a，详设§3.5.6 / §2.21.2 / DC-005)。

- POST /api/v1/paper/buy：买入(原子事务, §8.4)
- POST /api/v1/paper/sell：卖出
- POST /api/v1/paper/reset：重置(二次确认, §3.5.7)
- GET /api/v1/paper/portfolio：持仓看板

成交 NAV 来自 navs 真实收盘净值(§3.5.7)；不连通实盘。
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Any

import pandas as pd
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from api.deps import get_db
from api.services.paper import PaperTradingService
from schemas.envelope import SOURCE_BATCH, SOURCE_REALTIME, Envelope
from schemas.paper import BuyRequest, ResetRequest, SellRequest

router = APIRouter(prefix="/paper", tags=["paper"])


@router.post("/buy", summary="买入(§3.5.6, 原子事务)")
def buy(
    req: BuyRequest,
    db: Annotated[Session, Depends(get_db)],
) -> Envelope[dict[str, Any]]:
    """买入：扣现金 + 增持仓 + 记流水(原子事务 §8.4)。T 日净值成交(§3.5.7)。"""
    svc = PaperTradingService(db)
    td = date.fromisoformat(req.trade_date) if req.trade_date else None
    result = svc.buy(
        req.code,
        amount=req.amount,
        shares=req.shares,
        trade_date=td,
    )
    return Envelope.ok(data=result, source=SOURCE_REALTIME, as_of=date.today())


@router.post("/sell", summary="卖出(§3.5.6)")
def sell(
    req: SellRequest,
    db: Annotated[Session, Depends(get_db)],
) -> Envelope[dict[str, Any]]:
    """卖出：减持仓 + 增现金 + 记流水(原子事务 §8.4)。"""
    svc = PaperTradingService(db)
    td = date.fromisoformat(req.trade_date) if req.trade_date else None
    result = svc.sell(
        req.code,
        shares=req.shares,
        amount=req.amount,
        trade_date=td,
    )
    return Envelope.ok(data=result, source=SOURCE_REALTIME, as_of=date.today())


@router.get("/portfolio", summary="持仓看板(§3.5.3)")
def portfolio(
    db: Annotated[Session, Depends(get_db)],
    account_id: str = Query(default="default", description="账户 ID"),
) -> Envelope[dict[str, Any]]:
    """持仓看板：现金/总资产/盈亏/持仓明细。"""
    svc = PaperTradingService(db)
    result = svc.get_portfolio(account_id)
    return Envelope.ok(data=result, source=SOURCE_REALTIME, as_of=date.today())


@router.post("/reset", summary="重置账户(§3.5.7, 二次确认)")
def reset(
    req: ResetRequest,
    db: Annotated[Session, Depends(get_db)],
    account_id: str = Query(default="default", description="账户 ID"),
) -> Envelope[dict[str, Any]]:
    """重置：清仓 + 现金回初始(需二次确认 confirm=True)。"""
    svc = PaperTradingService(db)
    result = svc.reset(account_id, confirm=req.confirm)
    return Envelope.ok(data=result, source=SOURCE_REALTIME, as_of=date.today())


class DividendRequest(BaseModel):
    """POST /api/paper/dividend 分红调整(§3.5.4 / E3)。"""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(description="基金代码")
    div_per_unit: Decimal = Field(description="每份分红(元)")
    ex_nav: Decimal = Field(description="除息日单位净值")
    mode: str = Field(default="reinvest", description="reinvest(再投)/cash(现金)")


@router.post("/dividend", summary="分红复权调整(§3.5.4, E3)")
def dividend(
    req: DividendRequest,
    db: Annotated[Session, Depends(get_db)],
    account_id: str = Query(default="default", description="账户 ID"),
) -> Envelope[dict[str, Any]]:
    """分红复权：调整持仓份额(再投)或记现金分红(§3.5.4 / E3)。

    E3：后复权净值(adj_nav)已含分红再投，回测不调用本函数(删 DIVIDEND_MODE)；
    本端点用于单位净值成交场景的分红份额调整。
    """
    svc = PaperTradingService(db)
    result = svc.apply_dividend(
        req.code,
        req.div_per_unit,
        req.ex_nav,
        account_id=account_id,
        mode=req.mode,
    )
    return Envelope.ok(data=result, source=SOURCE_REALTIME, as_of=date.today())


@router.get("/breakeven", summary="回本测算(§3.5.2, FR-18/DC-011)")
def breakeven(
    db: Annotated[Session, Depends(get_db)],
    code: str = Query(description="基金代码"),
    account_id: str = Query(default="default", description="账户 ID"),
) -> Envelope[dict[str, Any]]:
    """回本测算：持仓亏损率 -> 回本需涨 |r|/(1+r)(§3.5.2 / FR-18)。"""
    svc = PaperTradingService(db)
    result = svc.get_breakeven(code, account_id=account_id)
    return Envelope.ok(data=result, source=SOURCE_REALTIME, as_of=date.today())


class DcaBacktestRequest(BaseModel):
    """POST /api/paper/dca-backtest 定投回测(§3.5.8 / TP-04)。"""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(description="基金代码")
    freq: str = Field(default="monthly", description="频率(weekly/monthly/quarterly)")
    amount: float = Field(default=1000.0, description="每期金额(元)")
    start: str | None = Field(default=None, description="起始日期(YYYY-MM-DD)")
    end: str | None = Field(default=None, description="结束日期(YYYY-MM-DD)")


@router.post("/dca-backtest", summary="定投回测(§3.5.8, TP-04, E3)")
def dca_backtest(
    req: DcaBacktestRequest,
    db: Annotated[Session, Depends(get_db)],
) -> Envelope[dict[str, Any]]:
    """历史定投回测：回放后复权净值(AdjNAV, E3) + 申购费 + 赎回费 + IRR。"""
    from domain.backtest_dca import run_dca

    # 从 DB 读后复权净值
    start = date.fromisoformat(req.start) if req.start else date(2020, 1, 1)
    end = date.fromisoformat(req.end) if req.end else date.today()
    nav = _load_adj_nav(db, req.code, start, end)
    if nav is None or len(nav) < 2:
        return Envelope.ok(
            data={"available": False, "note": "净值数据不足"},
            source=SOURCE_REALTIME,
            as_of=date.today(),
        )
    result = run_dca(nav, freq=req.freq, amount=req.amount)
    data = result.to_dict()
    data["code"] = req.code
    return Envelope.ok(data=data, source=SOURCE_BATCH, as_of=date.today())


def _load_adj_nav(db: Session, code: str, start: date, end: date) -> pd.Series | None:
    """从 DB 读后复权净值序列(复用 EvaluationService 逻辑)。"""
    from sqlalchemy import select

    from infra.db.models import Nav

    rows = db.execute(
        select(Nav.trade_date, Nav.adj_nav)
        .where(Nav.code == code, Nav.trade_date >= start, Nav.trade_date <= end)
        .order_by(Nav.trade_date)
    ).all()
    if not rows:
        return None
    dates = [r.trade_date for r in rows]
    values = [float(r.adj_nav) for r in rows if r.adj_nav is not None]
    return pd.Series(values, index=pd.to_datetime(dates)) if values else None


__all__: list[str] = ["router"]
