"""单基深度实验室接口(P1-09b，详设§3.8 / DC-011 / FR-40~42)。

- GET /api/v1/funds/{code}/breakeven   回本测算(三情景回本月数)
- GET /api/v1/funds/{code}/scenarios   三情景推演(保守/基准/乐观)
- GET /api/v1/funds/{code}/strategies   五策略对照

输入收益率来自数据中心真实净值(§3.8.6 OQ-25，禁止编造)；统一七字段信封(§2.21)。
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

import pandas as pd
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.deps import get_db
from infra.db.models import Fund, Nav
from schemas.envelope import SOURCE_BATCH, SOURCE_REALTIME, Envelope
from schemas.errors import NotFoundError

router = APIRouter(tags=["laboratory"])

#: 默认窗口(用于计算当前收益率与策略对照)。
DEFAULT_WINDOW_DAYS = 252


@router.get("/funds/{code}/breakeven", summary="回本测算(§3.8.2, FR-40)")
def lab_breakeven(
    code: str,
    db: Annotated[Session, Depends(get_db)],
    window: int = Query(default=DEFAULT_WINDOW_DAYS, ge=10, le=5000, description="回看窗口(交易日)"),
) -> Envelope[dict[str, Any]]:
    """回本测算：当前收益率 -> 回本需涨 + 三情景回本月数。"""
    from domain.laboratory import breakeven_analysis

    nav = _load_nav_series(db, code, days=window)
    if nav is None:
        raise NotFoundError(f"基金或净值不存在: {code}")
    ret = _current_return(nav)
    result = breakeven_analysis(ret)
    data = result.to_dict()
    data["code"] = code
    data["window_days"] = window
    return Envelope.ok(data=data, source=SOURCE_REALTIME, as_of=date.today())


@router.get("/funds/{code}/scenarios", summary="三情景推演(§3.8.2, FR-41)")
def lab_scenarios(
    code: str,
    db: Annotated[Session, Depends(get_db)],
    months: int = Query(default=12, ge=1, le=60, description="投影月数"),
) -> Envelope[dict[str, Any]]:
    """三情景推演：保守/基准/乐观 N 月净值投影。"""
    from domain.laboratory import scenario_projection

    nav = _load_nav_series(db, code, days=DEFAULT_WINDOW_DAYS)
    if nav is None:
        raise NotFoundError(f"基金或净值不存在: {code}")
    result = scenario_projection(nav, months=months)
    data = result.to_dict()
    data["code"] = code
    return Envelope.ok(data=data, source=SOURCE_BATCH, as_of=date.today())


@router.get("/funds/{code}/strategies", summary="五策略对照(§3.8.2, FR-42)")
def lab_strategies(
    code: str,
    db: Annotated[Session, Depends(get_db)],
    window: int = Query(default=DEFAULT_WINDOW_DAYS, ge=20, le=5000, description="回测窗口(交易日)"),
) -> Envelope[list[dict[str, Any]]]:
    """五策略对照：持有/定投/波段/调仓/止损 同窗口终值/收益/回撤。"""
    from domain.laboratory import strategy_comparison

    nav = _load_nav_series(db, code, days=window)
    if nav is None:
        raise NotFoundError(f"基金或净值不存在: {code}")
    results = strategy_comparison(nav)
    data = [r.to_dict() | {"code": code} for r in results]
    return Envelope.ok(data=data, source=SOURCE_BATCH, as_of=date.today())


def _load_nav_series(db: Session, code: str, *, days: int) -> pd.Series | None:
    """从 DB 读后复权净值序列(最近 N 日；用于实验室)。"""
    if db.get(Fund, code) is None:
        return None
    rows = db.execute(
        select(Nav.trade_date, Nav.adj_nav)
        .where(Nav.code == code)
        .order_by(Nav.trade_date.desc())
        .limit(days)
    ).all()
    if not rows:
        return None
    rows = list(reversed(rows))  # 升序
    dates = [r.trade_date for r in rows]
    values = [float(r.adj_nav) for r in rows if r.adj_nav is not None]
    if not values:
        return None
    return pd.Series(values, index=pd.to_datetime(dates))


def _current_return(nav: pd.Series) -> float:
    """当前收益率 = 末日/首日 - 1(§3.8.6 真实净值口径)。"""
    if len(nav) < 2:
        return 0.0
    start = float(nav.iloc[0])
    end = float(nav.iloc[-1])
    if start <= 0:
        return 0.0
    return end / start - 1.0


__all__: list[str] = ["router"]
