"""Mock 信封与数据形状单测(详设§2.21.1 七字段 / §4.2 错误码 / DC-011 回本)。"""

from __future__ import annotations

import pytest

from app import utils
from app.mock import envelope, store

SEVEN_FIELDS = {"code", "data", "source", "as_of", "disclaimer", "message", "trace_id"}


class TestMockEnvelope:
    """七字段信封(§2.21.1；CLAUDE.md§6 简写漏 disclaimer，以详设为准)。"""

    def test_ok_seven_fields(self) -> None:
        env = envelope.ok({"x": 1})
        assert set(env.keys()) == SEVEN_FIELDS

    def test_ok_source_mock(self) -> None:
        env = envelope.ok({"x": 1})
        assert env["code"] == 0
        assert env["source"] == "mock"
        assert env["disclaimer"] == "仅供参考，不构成投资建议"
        assert env["data"] == {"x": 1}

    def test_fail_data_null_disclaimer_none(self) -> None:
        env = envelope.fail(50303, "LLM 超时降级")
        assert env["code"] == 50303
        assert env["data"] is None
        assert env["disclaimer"] is None  # §7.3 失败体


class TestStoreData:
    def test_funds_have_required_fields(self) -> None:
        for f in store.FUNDS:
            for k in ("code", "name", "type", "scale_yi", "score"):
                assert k in f, f"基金 {f.get('code')} 缺字段 {k}"

    def test_default_weights_sum_one(self) -> None:
        assert sum(store.DEFAULT_WEIGHTS.values()) == pytest.approx(1.0)
        # ret 权重最高(TP-01 §3.1)
        assert store.DEFAULT_WEIGHTS["ret"] == 0.30

    def test_five_factors(self) -> None:
        assert tuple(store.DEFAULT_WEIGHTS) == ("ret", "risk", "perf", "scale", "manager")

    def test_score_composite_consistent(self) -> None:
        """composite 应等于五因子加权重算(ADR-002 一致)。"""
        for code, sc in store.SCORES.items():
            computed = utils.weighted_composite(sc["factors"], store.DEFAULT_WEIGHTS)
            assert abs(computed - sc["composite"]) < 1.0, f"{code} composite 不一致"

    def test_breakeven(self) -> None:
        assert store.breakeven_need(-0.30) == pytest.approx(0.428571, rel=1e-3)

    def test_dashboard_top10_sorted(self) -> None:
        rows = store.dashboard_top10()
        scores = [r["score"] for r in rows]
        assert scores == sorted(scores, reverse=True)

    def test_dashboard_top10_filter(self) -> None:
        rows = store.dashboard_top10("bond")
        assert all(r["type"] == "债券型" for r in rows)

    def test_fund_by_code(self) -> None:
        assert store.fund_by_code("110011") is not None
        assert store.fund_by_code("NOT_EXIST") is None

    def test_nav_series_no_future(self) -> None:
        """净值序列仅含历史区间(禁未来函数)。"""
        navs = store.nav_series("110011", days=30)
        assert len(navs) == 30
        assert all(n["trade_date"] <= store.AS_OF.isoformat() for n in navs)
        assert all(n["adj_nav"] > 0 for n in navs)  # NAV=0 不崩溃


class TestFundFees:
    """基金费率(申购/赎回/管理/托管/年综合；CLAUDE.md §4 费率预警>2% E9/E12)。"""

    def test_management_fee_from_fee_rate(self) -> None:
        f = store.fund_by_code("110011")
        fees = store.fund_fees(f)
        assert fees["management_fee"] == f["fee_rate"]  # 管理费取 fee_rate

    def test_total_fee_warn_threshold(self) -> None:
        """QDII 综合费率>2% 触发预警(E9/E12)。"""
        fees = store.fund_fees(store.fund_by_code("000934"))
        assert fees["total_fee"] > 0.02
        # 其他类型不触发
        assert store.fund_fees(store.fund_by_code("110011"))["total_fee"] < 0.02

    def test_etf_zero_buy_fee(self) -> None:
        """ETF 场内佣金另算，申购费 0。"""
        fees = store.fund_fees(store.fund_by_code("000961"))
        assert fees["buy_fee"] == 0.0

    def test_money_zero_fees(self) -> None:
        fees = store.fund_fees(store.fund_by_code("000509"))
        assert fees["buy_fee"] == 0.0 and fees["redemption_fee"] == 0.0

    def test_total_fee_is_mgmt_plus_custody(self) -> None:
        for c in ("110011", "000961", "000934"):
            fees = store.fund_fees(store.fund_by_code(c))
            assert fees["total_fee"] == round(fees["management_fee"] + fees["custody_fee"], 4)


class TestAttributionBoundary:
    """Brinson 边界(原型③)：仅 mixed/stock；index/etf 替代；bond 不显示(E1/E2)。"""

    def test_mixed_has_attribution(self) -> None:
        assert "110011" in store.ATTRIBUTION
        a = store.ATTRIBUTION["110011"]
        assert a["scope"] == "mixed/stock"
        # 三效应
        for k in ("allocation", "selection", "interaction"):
            assert k in a

    def test_substitute_messages(self) -> None:
        assert "跟踪误差" in store.ATTRIBUTION_SUBSTITUTE["index"]
        assert "不显示" in store.ATTRIBUTION_SUBSTITUTE["bond"]


class TestMetricsSummary:
    """指标摘要(供筛选/排序；优先 METRICS，缺失按类型回退)。"""

    def test_from_metrics_when_present(self) -> None:
        # 110011 有 METRICS 行 -> 与页03 指标卡同源
        m = store.fund_metrics_summary("110011")
        assert m["return_pct"] == store.METRICS["110011"]["年化收益"]
        assert m["max_drawdown"] == store.METRICS["110011"]["最大回撤"]
        assert m["sharpe"] == store.METRICS["110011"]["夏普比率"]

    def test_fallback_by_type(self) -> None:
        # 161725(stock) 无 METRICS -> 走 stock 回退
        m = store.fund_metrics_summary("161725")
        assert m == store._METRICS_FALLBACK["stock"]

    def test_unknown_code(self) -> None:
        m = store.fund_metrics_summary("NOT_EXIST")
        assert m == store._METRICS_FALLBACK["mix"]  # 默认 mix


class TestManagerTenure:
    def test_from_launch_date(self) -> None:
        # 110011 成立 2007-04-11 -> 至 2025-07-20 约 18 年
        assert store.fund_manager_tenure_years("110011") >= 15.0

    def test_unknown_code(self) -> None:
        assert store.fund_manager_tenure_years("NOPE") == 5.0


class TestScreenFunds:
    """筛选器口径(滑杆百分点 vs 指标比率 ÷100)与排序。"""

    def test_type_filter(self) -> None:
        from app import api_client

        rows = api_client.screen_funds({"fund_type": "bond"})
        assert rows and all(r["type"] == "bond" for r in rows)

    def test_max_drawdown_filter(self) -> None:
        """回撤 ≤ 20% -> |drawdown| ≤ 0.20(回撤为负，drawdown ≥ -0.20)。"""
        from app import api_client

        rows = api_client.screen_funds({"max_drawdown": 20})
        for r in rows:
            assert store.fund_metrics_summary(r["code"])["max_drawdown"] >= -0.20

    def test_min_return_filter(self) -> None:
        from app import api_client

        rows = api_client.screen_funds({"min_return": 8})
        for r in rows:
            assert store.fund_metrics_summary(r["code"])["return_pct"] >= 0.08

    def test_min_tenure_filter(self) -> None:
        from app import api_client

        rows = api_client.screen_funds({"min_tenure": 15})
        assert all(store.fund_manager_tenure_years(r["code"]) >= 15 for r in rows)

    def test_sort_by_score(self) -> None:
        from app import api_client

        rows = api_client.screen_funds({}, sort_by="综合评分")
        scores = [r["score"] for r in rows]
        assert scores == sorted(scores, reverse=True)

    def test_sort_by_drawdown(self) -> None:
        """回撤排序：回撤小(优)在前(回撤为负值，-0.0001 优于 -0.22，故降序)。"""
        from app import api_client

        rows = api_client.screen_funds({}, sort_by="回撤")
        draws = [store.fund_metrics_summary(r["code"])["max_drawdown"] for r in rows]
        assert draws == sorted(draws, reverse=True)  # 降序：最优(接近0)在前

    def test_sort_by_sharpe_descending(self) -> None:
        from app import api_client

        rows = api_client.screen_funds({}, sort_by="夏普")
        sharpes = [store.fund_metrics_summary(r["code"])["sharpe"] for r in rows]
        assert sharpes == sorted(sharpes, reverse=True)
