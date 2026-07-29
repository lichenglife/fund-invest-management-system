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
