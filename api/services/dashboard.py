"""仪表盘聚合服务(P1-12，详设§3.13 / DC-001 / FR-D1~D6)。

聚合首页四区：状态卡 / Top10 榜单 / 近期动态 / 学一基。
复用 scores 表(ADR-002 唯一权威源，只读)；缺失表降级(§2.15)。
缓存(§3.13.5)：fund:dashboard:{account_id} 5min、fund:top10:{type} 15min。
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from infra.db.models import Fund, FundDividend, Score

logger = logging.getLogger(__name__)

#: 默认账户。
DEFAULT_ACCOUNT = "default"

#: Top10 榜单默认类型。
DEFAULT_TOP_TYPE = "mixed"

#: 动态回看天数。
DYNAMICS_DAYS = 30


class DashboardService:
    """仪表盘聚合查询(§3.13)。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def aggregate(
        self, *, account_id: str = DEFAULT_ACCOUNT, fund_type: str = DEFAULT_TOP_TYPE
    ) -> dict[str, Any]:
        """聚合仪表盘视图(§3.13.2 / §2.21.2 schema)。

        顶层缓存由调用方(endpoint)持有 fund:dashboard:{account_id}:{type}；本方法仅聚合，
        子缓存 fund:top10:{type} 在 ``_top10`` 内部。
        """
        view: dict[str, Any] = {
            "portfolio_return": self._portfolio_return(account_id),
            "benchmark_return": None,  # MVP：基准收益待 macro 模块(P2-01)
            "todos": self._todos(account_id),
            "learning_progress": 0.0,  # learning_paths 未建(D2) -> 0
            "top10": self._top10(fund_type),
            "dynamics": self._dynamics(),
            "learn_one": self._learn_one(),
        }
        return view

    # ------------------------------------------------------------------
    # 状态卡
    # ------------------------------------------------------------------

    def _portfolio_return(self, account_id: str) -> float | None:
        """组合/账户收益率(MVP：无实盘 -> None)。"""
        # TODO(P3)：接 paper/portfolio 收益聚合
        return None

    def _todos(self, account_id: str) -> list[dict[str, str]]:
        """待办(MVP：组合再平衡提醒，FR-24)。"""
        # MVP：无组合配置时返回空待办(§2.15 降级)
        return []

    # ------------------------------------------------------------------
    # Top10 榜单(ADR-002 只读 scores)
    # ------------------------------------------------------------------

    def _top10(self, fund_type: str) -> list[dict[str, Any]]:
        """类型 Tab Top10 综合评分(§3.13.2 / DC-003 唯一权威源)。

        ``fund_type=all`` 跨类型取 Top10；否则按类型过滤。
        """
        from infra.redis.cache import cache_get, cache_set

        cached = cache_get("top10", type=fund_type)
        if cached is not None:
            return list(cached)

        stmt = (
            select(Fund.code, Fund.name, Fund.type_, Score.composite, Score.as_of)
            .join(Score, Score.code == Fund.code)
            .order_by(Score.composite.desc())
            .limit(10)
        )
        if fund_type != "all":
            stmt = stmt.where(Fund.type_ == fund_type)
        rows = self.db.execute(stmt).all()
        items = [
            {
                "code": r.code,
                "name": r.name,
                "type": r.type_,
                "score": round(float(r.composite), 2) if r.composite is not None else None,
                "as_of": r.as_of.isoformat() if r.as_of else None,
            }
            for r in rows
        ]
        cache_set("top10", type=fund_type, value=items)
        return items

    # ------------------------------------------------------------------
    # 近期动态
    # ------------------------------------------------------------------

    def _dynamics(self) -> list[dict[str, Any]]:
        """近期动态：分红/新发/异动(§3.13.2)。

        fund_dividends 表有数据 -> 分红事件；新发基金(近 30 日 launch_date)。
        缺失表降级为空(§2.15)。
        """
        items: list[dict[str, Any]] = []
        since = date.today() - timedelta(days=DYNAMICS_DAYS)

        # 分红事件
        try:
            divs = self.db.execute(
                select(FundDividend.code, FundDividend.ex_date, FundDividend.div_per_unit)
                .where(FundDividend.ex_date >= since)
                .order_by(FundDividend.ex_date.desc())
                .limit(10)
            ).all()
            for d in divs:
                items.append({
                    "type": "dividend",
                    "title": f"{d.code} 分红 {d.div_per_unit}",
                    "date": d.ex_date.isoformat() if d.ex_date else None,
                })
        except Exception as exc:  # noqa: BLE001
            logger.warning("dashboard.dividends_failed", extra={"err": str(exc)})

        # 新发基金
        try:
            new_funds = self.db.execute(
                select(Fund.code, Fund.name, Fund.launch_date)
                .where(Fund.launch_date >= since)
                .order_by(Fund.launch_date.desc())
                .limit(10)
            ).all()
            for f in new_funds:
                items.append({
                    "type": "new",
                    "title": f"新发基金 {f.name}",
                    "date": f.launch_date.isoformat() if f.launch_date else None,
                })
        except Exception as exc:  # noqa: BLE001
            logger.warning("dashboard.new_funds_failed", extra={"err": str(exc)})

        return items

    # ------------------------------------------------------------------
    # 学一基卡
    # ------------------------------------------------------------------

    def _learn_one(self) -> dict[str, Any]:
        """学一基：自动摘要基金档案 + 词典链接(§3.13.2)。

        MVP：取评分最高的一只基金作为"学一基"。
        """
        row = self.db.execute(
            select(Fund.code, Fund.name, Fund.type_, Score.composite)
            .join(Score, Score.code == Fund.code)
            .order_by(Score.composite.desc())
            .limit(1)
        ).first()
        if row is None:
            return {"available": False, "note": "暂无评分数据"}
        return {
            "available": True,
            "code": row.code,
            "name": row.name,
            "type": row.type_,
            "score": round(float(row.composite), 2) if row.composite is not None else None,
            "glossary_links": ["score", "type", "nav", "adj_nav"],
        }


__all__: list[str] = ["DashboardService", "DEFAULT_ACCOUNT"]
