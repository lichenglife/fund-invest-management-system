"""数据中心服务层(P1-02a/b，详设§3.2 / §2.21 契约)。

从 DB 读 Fund/Nav/Holding/Score，返回符合前端消费 shape 的数据。
缺失字段(managers/discovery_entries/field_glossary 表未建, DEFERRED D2/D7)
降级为 None / 空集 / 50301，不阻塞核心查询(§2.15)。

> 评估引擎唯一权威源(ADR-002)：本层只读 Score 表，不本地重算评分。
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from infra.db.models import Fund, Holding, Nav
from infra.db.models.fund import Score as ScoreModel

logger = logging.getLogger(__name__)

#: 单页上限(§2.21.1 分页)。
MAX_PAGE_SIZE = 100


class DataService:
    """数据中心查询服务(§3.2 / 注入 DB session)。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # P1-02a 检索 / 分类树 / 发现
    # ------------------------------------------------------------------

    def search_funds(
        self,
        *,
        q: str | None = None,
        fund_type: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """基金检索/列表(§3.2.2：代码/拼音/名称 SQL 模糊匹配 + 类型过滤 + 分页)。

        LEFT JOIN Score 取 composite(ADR-002 只读批算结果)。
        """
        page = max(1, page)
        page_size = max(1, min(page_size, MAX_PAGE_SIZE))

        stmt = select(Fund).order_by(Fund.code)
        if q:
            like = f"%{q}%"
            stmt = stmt.where(
                or_(Fund.code.ilike(like), Fund.name.ilike(like), Fund.theme.ilike(like))
            )
        if fund_type and fund_type != "all":
            stmt = stmt.where(Fund.type_ == fund_type)

        total = self.db.execute(
            select(func.count()).select_from(stmt.subquery())
        ).scalar_one()

        rows = self.db.execute(
            stmt.offset((page - 1) * page_size).limit(page_size)
        ).scalars().all()

        score_map = self._score_map([f.code for f in rows])
        items = [self._fund_brief(f, score_map.get(f.code)) for f in rows]
        return {"items": items, "total": int(total), "page": page, "page_size": page_size}

    def fund_tree(self) -> dict[str, Any]:
        """分类树(§3.2.2：按 type/sub_type 聚合计数)。"""
        rows = self.db.execute(
            select(Fund.type_, Fund.sub_type, func.count()).group_by(Fund.type_, Fund.sub_type)
        ).all()
        tree: dict[str, dict[str, Any]] = {}
        for type_, sub_type, cnt in rows:
            tree.setdefault(type_ or "unknown", {"count": 0, "children": {}})
            tree[type_]["count"] += int(cnt)
            if sub_type:
                tree[type_]["children"][sub_type] = int(cnt)
        # children dict -> list
        for node in tree.values():
            node["children"] = [{"name": k, "count": v} for k, v in node["children"].items()]
        return {"tree": list(tree.values()), "types": list(tree.keys())}

    def discovery(self) -> dict[str, Any]:
        """发现入口(§3.2.2：signal/ranking/learn 推荐)。

        discovery_entries 表未建(DEFERRED D2) -> 降级返回空 + note(§2.15 不阻塞)。
        """
        return {
            "items": [],
            "available": False,
            "note": "发现入口(discovery_entries)待 P2 落地(DEFERRED D2)",
        }

    # ------------------------------------------------------------------
    # P1-02b 档案 / 净值 / 盘中 / 下载 / 持仓 / 经理
    # ------------------------------------------------------------------

    def get_fund_profile(self, code: str) -> dict[str, Any] | None:
        """基金档案(§3.2.2：档案分组 + 最新净值 + 评分)。

        managers 表未建(D2) -> company/manager/tenure_return/fee_rate/scale_yi 降级 None。
        """
        fund = self.db.get(Fund, code)
        if fund is None:
            return None
        latest_nav = self._latest_nav(code)
        score = self._score_map([code]).get(code)
        return self._fund_detail(fund, latest_nav, score)

    def get_nav_series(self, code: str, *, days: int = 252) -> list[dict[str, Any]] | None:
        """净值序列(§3.2.2：unit/acc/adj 三列 + is_estimate 标注)。"""
        if self.db.get(Fund, code) is None:
            return None
        rows = self.db.execute(
            select(Nav)
            .where(Nav.code == code)
            .order_by(Nav.trade_date.desc())
            .limit(max(1, days))
        ).scalars().all()
        rows = list(reversed(rows))  # 升序输出(便于绘图)
        return [
            {
                "date": r.trade_date.isoformat(),
                "nav": float(r.nav),
                "acc_nav": float(r.acc_nav) if r.acc_nav is not None else None,
                "adj_nav": float(r.adj_nav),
                "is_estimate": bool(r.is_estimate),
            }
            for r in rows
        ]

    def get_intraday(self, code: str) -> dict[str, Any] | None:
        """盘中估算(§3.2.2 / §3.2.7)。

        盘中数据表未建 -> 降级返最新净值并标 is_estimate=True + disclaimer(§3.2.7)。
        """
        if self.db.get(Fund, code) is None:
            return None
        latest = self._latest_nav(code)
        if latest is None:
            return {"code": code, "nav": None, "is_estimate": True, "available": False}
        return {
            "code": code,
            "nav": latest["nav"],
            "acc_nav": latest.get("acc_nav"),
            "is_estimate": True,
            "available": True,
            "note": "盘中估算待落地(降级为最新净值)，仅供参考，以收盘净值为准(§3.2.7)",
        }

    def get_holdings(self, code: str) -> list[dict[str, Any]] | None:
        """前十大持仓 + 行业分布(§3.2.2)。"""
        if self.db.get(Fund, code) is None:
            return None
        row = self.db.execute(
            select(Holding.report_date)
            .where(Holding.code == code)
            .order_by(Holding.report_date.desc())
            .limit(1)
        ).first()
        if row is None:
            return []
        rows = self.db.execute(
            select(Holding).where(Holding.code == code, Holding.report_date == row.report_date)
        ).scalars().all()
        return [
            {
                "stock_code": h.stock_code,
                "stock_name": h.stock_name,
                "weight": float(h.weight) if h.weight is not None else None,
                "report_date": h.report_date.isoformat(),
            }
            for h in rows
        ]

    def get_manager(self, code: str) -> dict[str, Any] | None:
        """经理风格箱(§3.2.2)。

        managers 表未建(DEFERRED D2) -> 调用方应返 50301；此处置 None。
        """
        fund = self.db.get(Fund, code)
        if fund is None:
            return None  # 基金不存在 -> 40002
        return None  # managers 表未建 -> 50301 由路由层判定

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _latest_nav(self, code: str) -> dict[str, Any] | None:
        row = self.db.execute(
            select(Nav).where(Nav.code == code).order_by(Nav.trade_date.desc()).limit(1)
        ).scalars().first()
        if row is None:
            return None
        return {
            "date": row.trade_date.isoformat(),
            "nav": float(row.nav),
            "acc_nav": float(row.acc_nav) if row.acc_nav is not None else None,
            "adj_nav": float(row.adj_nav),
            "is_estimate": bool(row.is_estimate),
        }

    def _score_map(self, codes: list[str]) -> dict[str, dict[str, Any]]:
        """批量取评分(ADR-002 唯一权威源，只读)。"""
        if not codes:
            return {}
        rows = self.db.execute(
            select(ScoreModel).where(ScoreModel.code.in_(codes))
        ).scalars().all()
        return {
            r.code: {
                "score": float(r.composite),
                "weights": r.weights,
                "factors": r.factors,
                "as_of": r.as_of.isoformat() if r.as_of else None,
            }
            for r in rows
        }

    def _fund_brief(self, fund: Fund, score: dict[str, Any] | None) -> dict[str, Any]:
        """列表项(对齐前端 mock FUNDS shape)。"""
        return {
            "code": fund.code,
            "name": fund.name,
            "type": fund.type_,
            "sub_type": fund.sub_type,
            "theme": fund.theme,
            "style": fund.style,
            "launch_date": fund.launch_date.isoformat() if fund.launch_date else None,
            "score": score["score"] if score else None,
            # 以下字段 managers/scale 表未建(D2/D7) -> 降级 None
            "scale_yi": None,
            "manager": None,
            "tenure_return": None,
            "fee_rate": None,
            "company": None,
        }

    def _fund_detail(
        self,
        fund: Fund,
        latest_nav: dict[str, Any] | None,
        score: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """档案详情(对齐前端 fund_by_code shape + 最新净值)。"""
        data = self._fund_brief(fund, score)
        data["nav"] = latest_nav
        return data


__all__: list[str] = ["DataService", "MAX_PAGE_SIZE"]
