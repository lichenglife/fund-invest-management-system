"""评估服务层(P1-04a，详设§3.3 评估引擎 / §3.3.5 缓存 / §3.3.7 溯源)。

从 DB 读 NAV/持仓，调 domain 算法层(metrics/scoring/attribution/research)，
返回带 source/as_of/cv_flag 的结果(§3.3.7 溯源)。

> 评估引擎唯一权威源(ADR-002/§3.3.7)：本层是 domain 算法的唯一调用入口，
> 筛选器/仪表盘只读引用，不得本地重算。
> 缓存：fund:score:{code} TTL 30min(§3.3.5)；MVP 无 Redis 时降级直算(§8.5)。
"""

from __future__ import annotations

import logging
from datetime import date

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from domain.metrics import DEFAULT_EVAL_WINDOW, Metrics, compute_metrics
from domain.scoring import Score, multi_factor_score
from infra.db.models import Fund, Nav

logger = logging.getLogger(__name__)

#: 评分缓存 TTL(§3.3.5)。
SCORE_CACHE_TTL = 1800  # 30 min


class EvaluationService:
    """评估服务(§3.3 / ADR-002 唯一权威源入口)。

    依赖注入 DB session(§1.5)；便于测试隔离。
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------ 基础

    def get_fund(self, code: str) -> Fund | None:
        """查基金基础信息；不存在返 None。"""
        return self.db.get(Fund, code)

    def load_nav_series(self, code: str, *, window: str = DEFAULT_EVAL_WINDOW) -> pd.Series:
        """从 DB 读净值序列 -> pandas Series(index=trade_date, values=nav)。

        用 adj_nav(后复权净值，E3 红线)；按 window 截取近 N 年。
        Args:
            code: 基金代码。
            window: 评估窗口(默认 3Y)。
        """
        years = _parse_window_years(window)
        cutoff = date.today().replace(year=date.today().year - years)
        rows = self.db.execute(
            select(Nav.trade_date, Nav.adj_nav)
            .where(Nav.code == code, Nav.trade_date >= cutoff)
            .order_by(Nav.trade_date)
        ).all()
        if not rows:
            return pd.Series([], dtype=float)
        dates = [r.trade_date for r in rows]
        values = [float(r.adj_nav) for r in rows if r.adj_nav is not None]
        return pd.Series(values, index=pd.to_datetime(dates))

    # ------------------------------------------------------------------ 指标

    def get_metrics(
        self, code: str, *, window: str = DEFAULT_EVAL_WINDOW, benchmark: str | None = None
    ) -> Metrics | None:
        """计算核心指标(§3.3.2 / P1-03a)。

        基金不存在返 None(40002 由路由处理)；NAV 不足返 Metrics(全 None)。
        """
        fund = self.get_fund(code)
        if fund is None:
            return None
        nav = self.load_nav_series(code, window=window)
        bm: str | None = benchmark
        if bm == "auto":
            bm = None  # 让 compute_metrics 按 fund_type 自动选(DC-003)
        return compute_metrics(nav, benchmark=bm, window=window, fund_type=fund.type_)

    # ------------------------------------------------------------------ 评分

    def get_score(
        self, code: str, *, weights: dict[str, int] | None = None, window: str = DEFAULT_EVAL_WINDOW
    ) -> Score | None:
        """五因子评分(§3.3.8.1 / P1-03b)。

        单基金查询无横截面 universe -> 子分可能 None(需批算提供 universe)。
        MVP 阶段：universe 缺失时 scale 子分仍有效(非线性)，其余子分 None。
        """
        fund = self.get_fund(code)
        if fund is None:
            return None
        nav = self.load_nav_series(code, window=window)
        asset_class = _fund_type_to_asset_class(fund.type_)
        return multi_factor_score(code, nav=nav, asset_class=asset_class, weights=weights)

    # ------------------------------------------------------------------ 风格箱

    def get_stylebox(self, code: str) -> tuple[str | None, str | None] | None:
        """风格箱(size, value_growth)(§3.3.1 / 闭合 E13)。

        风格箱限权益类(详设 E13)；债/货/QDII 不显示。
        > P1-03 阶段 stylebox 算法未实现(P1-04a 仅占位)；
        > 返回 None 表示待实现，路由降级展示。
        """
        fund = self.get_fund(code)
        if fund is None:
            return None
        # TODO(P1-03 风格箱): domain/stylebox.py 待实现(持仓法+收益回归交叉验证)
        # 权益类返占位；非权益类不显示(E13)
        if fund.type_ in ("mixed", "stock", "index", "etf"):
            return (None, None)  # 占位：算法待实现
        return None  # 债/货/QDII 不显示(E13)


def _parse_window_years(window: str) -> int:
    """窗口串(3Y/1Y/5Y) -> 年数。"""
    w = window.upper().rstrip("Y")
    try:
        return int(w)
    except ValueError:
        return 3


def _fund_type_to_asset_class(fund_type: str) -> str:
    """基金 type -> 底层 asset_class(E5 分组维度)。

    映射(详设§3.3.8.1 asset_class: equity/debt/money/alt/qdii)：
    stock/mixed -> equity；bond -> debt；money -> money；qdii -> qdii；其余 alt。
    """
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


__all__: list[str] = ["EvaluationService", "SCORE_CACHE_TTL"]
