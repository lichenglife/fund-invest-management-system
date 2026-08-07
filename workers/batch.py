"""批算 worker 入口(P1-05，详设§3.3.9 / §3.14.2 工作日 18:30)。

夜算：全市场基金评分 -> 写 PG(scores) + 刷 Redis(fund:score:{code} TTL 30min)。
ProcessPoolExecutor 跨基金并行(§2.22.1)；评估引擎唯一权威源(ADR-002)。

运行：``python -m workers.batch``
TODO(§3.14.2)：APScheduler 18:30 触发(P1-01d scheduler 已建)。
"""

from __future__ import annotations

import json
import logging
from datetime import date
from decimal import Decimal
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from config.settings import get_settings
from domain.batch import FundRawInput, batch_score_all, build_percentile_tables
from domain.metrics import DEFAULT_EVAL_WINDOW
from infra.db.models import Fund, Nav
from infra.db.models import Score as ScoreModel
from infra.db.session import SessionLocal
from infra.logging import setup_logging
from infra.redis.client import get_redis

logger = logging.getLogger(__name__)

#: scores 缓存 TTL(§2.8 / §3.3.5，30min)。
SCORE_CACHE_TTL = 1800


def load_all_funds(db: Session, *, window: str = DEFAULT_EVAL_WINDOW) -> list[FundRawInput]:
    """从 DB 读全市场基金 -> FundRawInput(含 nav 序列,asset_class)。"""
    funds = db.execute(select(Fund)).scalars().all()
    result: list[FundRawInput] = []
    for f in funds:
        asset_class = _fund_type_to_asset_class(f.type_)
        nav = _load_nav(db, f.code, window=window)
        result.append(
            FundRawInput(
                code=f.code,
                asset_class=asset_class,
                nav=nav,
                aum=None,  # TODO(D7): funds 表无 aum 字段(详设§2.20.2)，待 P1-02 补
                manager_excess_val=None,
            )
        )
    return result


def run_once(*, window: str = DEFAULT_EVAL_WINDOW, trigger: str = "manual") -> dict[str, int]:
    """夜算单次：全市场评分 -> 写 PG + 刷 Redis(§3.3.9)；执行结果落库 scheduler_jobs(§3.14.3)。

    Returns:
        {"funds": N, "scored": M, "cached": K} 统计。
    """
    from domain.scheduler import record_job_run

    with record_job_run(
        "fund_recalc", "指标/评分重算", trigger=trigger, args={"window": window}
    ) as run:
        with SessionLocal() as db:
            funds = load_all_funds(db, window=window)
            pct = build_percentile_tables(funds, window=window)
            results = batch_score_all(funds, pct)
            # upsert scores 表(§3.3.9)
            scored = _upsert_scores(db, results)
            # 刷 Redis(§3.3.5 fund:score:{code} TTL 30min)
            cached = _cache_scores(results)
        result = {"funds": len(funds), "scored": scored, "cached": cached}
        run.result_summary = result
        logger.info(
            "batch.run_done",
            extra={"action": "batch", "funds": len(funds), "scored": scored, "cached": cached},
        )
        return result


def _upsert_scores(db: Session, results: dict[str, dict[str, Any]]) -> int:
    """upsert scores 表(§3.3.9，幂等 ON CONFLICT)。"""
    rows = []
    for code, res in results.items():
        if res.get("composite") is None:
            continue  # 货基/缺失跳过
        rows.append(
            {
                "code": code,
                "window": DEFAULT_EVAL_WINDOW,
                "weights": res.get("factors", {}),  # 简化：存因子结构
                "composite": Decimal(str(res["composite"])),
                "factors": res.get("factors", {}),
                "as_of": date.today(),
            }
        )
    if not rows:
        return 0
    stmt = pg_insert(ScoreModel).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=[ScoreModel.code],
        set_={
            "weights": stmt.excluded.weights,
            "composite": stmt.excluded.composite,
            "factors": stmt.excluded.factors,
            "as_of": stmt.excluded.as_of,
            "updated_at": stmt.excluded.updated_at,
        },
    )
    db.execute(stmt)
    db.commit()
    return len(rows)


def _cache_scores(results: dict[str, dict[str, Any]]) -> int:
    """刷 Redis fund:score:{code}(§3.3.5，TTL 30min)；无 Redis 跳过(§8.5)。"""
    client = get_redis()
    if client is None:
        logger.warning("batch.redis_unavailable", extra={"action": "cache", "degraded": True})
        return 0
    count = 0
    for code, res in results.items():
        if res.get("composite") is None:
            continue
        client.set(f"fund:score:{code}", json.dumps(res, default=str), ex=SCORE_CACHE_TTL)
        count += 1
    return count


def _load_nav(db: Session, code: str, *, window: str) -> pd.Series | None:
    """从 DB 读基金净值序列(复用 EvaluationService 逻辑)。"""
    years = 3 if "3" in window else 1
    # 闰年 2月29 安全(避免 date.replace 崩溃)
    today = date.today()
    try:
        cutoff = today.replace(year=today.year - years)
    except ValueError:
        cutoff = today.replace(month=2, day=28, year=today.year - years)
    rows = db.execute(
        select(Nav.trade_date, Nav.adj_nav)
        .where(Nav.code == code, Nav.trade_date >= cutoff)
        .order_by(Nav.trade_date)
    ).all()
    if not rows:
        return None
    dates = [r.trade_date for r in rows]
    values = [float(r.adj_nav) for r in rows if r.adj_nav is not None]
    return pd.Series(values, index=pd.to_datetime(dates)) if values else None


def _fund_type_to_asset_class(fund_type: str) -> str:
    """基金 type -> asset_class(E5 分组)。"""
    mapping = {
        "stock": "equity",
        "mixed": "equity",
        "bond": "debt",
        "money": "money",
        "qdii": "qdii",
        "index": "equity",
        "etf": "equity",
    }
    return mapping.get(fund_type, "alt")


def main() -> None:
    s = get_settings()
    setup_logging(level=s.log_level, service="fundlens-batch")
    stats = run_once()
    print(f"[batch] {stats}")


if __name__ == "__main__":
    main()
