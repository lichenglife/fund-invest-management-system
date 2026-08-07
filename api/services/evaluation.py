"""评估服务层(P1-04a/b，详设§3.3 评估引擎 / §3.3.5 缓存 / §3.3.7 溯源)。

从 DB 读 NAV/持仓，调 domain 算法层(metrics/scoring/attribution/research)，
返回带 source/as_of/cv_flag 的结果(§3.3.7 溯源)。

> 评估引擎唯一权威源(ADR-002/§3.3.7)：本层是 domain 算法的唯一调用入口，
> 筛选器/仪表盘只读引用，不得本地重算。
> 缓存：fund:score:{code} TTL 30min(§3.3.5)；MVP 无 Redis 时降级直算(§8.5)。
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from domain.attribution import Attribution, brinson_attribution
from domain.metrics import DEFAULT_EVAL_WINDOW, Metrics, compute_metrics
from domain.research import ERPResult, ProxyResult, erp_proxy, peg_proxy
from domain.scoring import SCORE_WEIGHTS, Score, recompute_with_weights
from domain.stylebox import STYLEBOX_SCOPE, StyleBoxResult, style_box
from infra.db.models import Fund, Holding, Nav
from infra.db.models.fund import Score as ScoreModel

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
        """从 DB 读净值序列 -> pandas Series(index=trade_date, values=adj_nav)。

        用 adj_nav(后复权净值，E3 红线)；按 window 截取近 N 年。
        """
        years = _parse_window_years(window)
        cutoff = _window_cutoff(years)  # 闰年 2月29 安全(避免 date.replace 崩溃)
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

    def load_holdings(self, code: str) -> list[dict[str, Any]]:
        """从 DB 读最新一期持仓 -> [{stock_code, stock_name, weight}]。"""
        row = self.db.execute(
            select(Holding.report_date)
            .where(Holding.code == code)
            .order_by(Holding.report_date.desc())
            .limit(1)
        ).first()
        if row is None:
            return []
        rows = self.db.execute(
            select(Holding.stock_code, Holding.stock_name, Holding.weight).where(
                Holding.code == code, Holding.report_date == row.report_date
            )
        ).all()
        return [
            {
                "stock": r.stock_code,
                "stock_name": r.stock_name,
                "weight": float(r.weight) if r.weight else 0.0,
            }
            for r in rows
        ]

    # ------------------------------------------------------------------ 指标

    def get_metrics(
        self, code: str, *, window: str = DEFAULT_EVAL_WINDOW, benchmark: str | None = None
    ) -> Metrics | None:
        """计算核心指标(§3.3.2 / P1-03a)。基金不存在返 None。"""
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

        ADR-002(唯一权威源)：在线查询读批算结果(``scores`` 表，P1-05 夜算产出)，
        不重算横截面百分位(§3.3.9)；可调权重时用存储的子分即时重算 composite
        (分位表不变)。批算未运行 -> composite=None(不在线重算百分位)。

        缓存(§2.8)：默认权重走 ``fund:score:{code}``(30min)；自定义权重不缓存。
        """
        # 默认权重 -> 读缓存(§2.8)
        from infra.redis.cache import cache_get, cache_set

        if weights is None:
            cached = cache_get("score", code=code)
            if cached is not None:
                # 缓存 schema 漂移(旧版本残留) -> 视为未命中，走 DB 重算并覆写
                try:
                    return Score(
                        code=cached["code"],
                        composite=cached["composite"],
                        factors=cached["factors"],
                        weights=cached.get("weights") or dict(SCORE_WEIGHTS),
                        as_of=cached.get("as_of"),
                    )
                except (KeyError, TypeError, ValueError):
                    logger.warning("score.cache_schema_drift code=%s", code)

        fund = self.get_fund(code)
        if fund is None:
            return None
        row = self.db.get(ScoreModel, code)
        if row is None:
            # 批算未运行：composite=None(ADR-002 禁止在线重算百分位)
            return Score(
                code=code,
                composite=None,
                weights=dict(SCORE_WEIGHTS),
                as_of=None,
            )
        stored_weights = row.weights or dict(SCORE_WEIGHTS)
        base = Score(
            code=code,
            composite=float(row.composite),
            factors=row.factors,
            weights=stored_weights,
            as_of=row.as_of.isoformat() if row.as_of else None,
        )
        # 可调权重：用存储子分即时重算(分位表不变, ADR-002)
        if weights is not None and weights != stored_weights:
            new_comp = recompute_with_weights(base, weights)
            return Score(
                code=code,
                composite=new_comp,
                factors=row.factors,
                weights=weights,
                as_of=base.as_of,
            )
        # 默认权重 -> 写缓存(§2.8)
        cache_set(
            "score",
            code=code,
            value={
                "code": base.code,
                "composite": base.composite,
                "factors": base.factors,
                "weights": base.weights,
                "as_of": base.as_of,
            },
        )
        return base

    # ------------------------------------------------------------------ 风格箱

    def get_stylebox(self, code: str) -> StyleBoxResult | None:
        """风格箱九宫格(size, value_growth)(§3.3.1 / TP-01 §3.5 / 闭合 E13)。

        调 domain.stylebox：持仓法(市值+估值成长因子)+收益回归交叉验证，E13 限权益类。
        基金不存在或类型不适用(E13)返 None；否则返 StyleBoxResult(数据不足时 available=False)。
        """
        fund = self.get_fund(code)
        if fund is None:
            return None
        if fund.type_ not in STYLEBOX_SCOPE:
            return None  # 债/货/QDII/另类不显示(E13)
        holdings = self.load_holdings(code)
        as_of = fund.as_of.isoformat() if fund.as_of else None
        return style_box(
            fund.type_,
            holdings,
            fund_style=fund.style,
            as_of=as_of,
        )

    # ------------------------------------------------------------------ Brinson 归因(P1-03c)

    def get_attribution(self, code: str) -> Attribution | None:
        """Brinson 业绩归因(§3.3.8.2 / P1-03c)。

        从 DB 读持仓构造 periods；基金不存在返 None。
        > MVP：基准成分权重/收益暂缺，用持仓做单期近似(基准缺失标 unavailable)。
        """
        fund = self.get_fund(code)
        if fund is None:
            return None
        hp = self.load_holdings(code)
        if not hp:
            return brinson_attribution(fund.type_, periods=[])
        # MVP：基准成分收益暂缺(D2/D7) -> unavailable=True，禁止返回误导性 0 值(§3.3.8.2)
        # 完整实现待基准成分数据采集(P1-02)后补 R_p/R_b
        return Attribution(
            unavailable=True,
            reason="benchmark_returns_missing",
            scope=fund.type_,
        )

    # ------------------------------------------------------------------ 研究指标(P1-03d)

    def get_research(self, code: str, *, rf_rate: float = 0.025) -> tuple[ProxyResult, ERPResult]:
        """PEG/ERP 代理 + 卡片(§3.3.7 / P1-03d)。

        从 DB 读持仓喂 peg_proxy/erp_proxy；持仓缺失时 available=False。
        rf_rate 默认 0.025(2.5%，10Y 国债近似)。
        """
        fund = self.get_fund(code)
        if fund is None:
            return ProxyResult(value=None, method="fund_missing", available=False), ERPResult(
                available=False, method="fund_missing"
            )
        hp = self.load_holdings(code)
        # 持仓无 pe/growth/ey 字段(DB holdings 表无) -> PEG/ERP available=False
        # 完整实现需 P1-01 补个股 PE/增长数据采集(D2)
        peg = peg_proxy(fund.type_, hp if hp else None, as_of=date.today().isoformat())
        erp = erp_proxy(
            fund.type_, hp if hp else None, rf_rate=rf_rate, as_of=date.today().isoformat()
        )
        return peg, erp


def _parse_window_years(window: str) -> int:
    """窗口串(3Y/1Y/5Y) -> 年数。"""
    w = window.upper().rstrip("Y")
    try:
        return int(w)
    except ValueError:
        return 3


def _window_cutoff(years: int) -> date:
    """计算 N 年前的截止日期(闰年 2月29 安全)。

    ``date.replace(year=year-N)`` 在 2月29 触发 ValueError；改用 3月1日回退1天，
    保证任意 today 都不崩(§4 红线：极值输入不崩溃)。
    """
    today = date.today()
    try:
        return today.replace(year=today.year - years)
    except ValueError:
        # 2月29 -> 回退到 2月28
        return today.replace(month=2, day=28, year=today.year - years)


def _fund_type_to_asset_class(fund_type: str) -> str:
    """基金 type -> 底层 asset_class(E5 分组维度)。"""
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
