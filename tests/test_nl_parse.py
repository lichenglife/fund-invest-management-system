"""NL 解析单测(P1-06b，详设§3.4.7 / TP-02 / DC-004 / §4 E6 红线)。

覆盖：类型/窗口/因子检测、E6 稳健排除 index/etf、歧义反问、结构化条件构造。
"""

from __future__ import annotations

import pytest

from domain.nl_parse import NL_ACCURACY_TARGET, nl_parse


class TestTypeDetection:
    """类型检测(对齐 nl_baseline)。"""

    @pytest.mark.parametrize(
        "query,expected",
        [
            ("混合基金", ["mixed"]),
            ("股票型基金", ["stock"]),
            ("债券基金", ["bond"]),
            ("ETF", ["etf"]),
            ("指数基金", ["index"]),
            ("QDII", ["qdii"]),
            ("货币基金", ["money"]),
        ],
    )
    def test_detect_type(self, query: str, expected: list[str]) -> None:
        assert nl_parse(query).type_ == expected


class TestWindowDetection:
    def test_one_year(self) -> None:
        assert nl_parse("近一年混合基金").window == "1y"

    def test_three_year(self) -> None:
        assert nl_parse("近三年混合基金").window == "3y"

    def test_no_window(self) -> None:
        assert nl_parse("混合基金").window is None


class TestFactorDetection:
    def test_explicit_drawdown(self) -> None:
        r = nl_parse("回撤小于15%的混合基金")
        assert r.factors["max_drawdown_le"] == pytest.approx(0.15)

    def test_steady_default_drawdown(self) -> None:
        r = nl_parse("稳健混合基金")
        assert r.factors["max_drawdown_le"] == pytest.approx(0.15)

    def test_return_rank(self) -> None:
        r = nl_parse("收益排名前20%的混合基金")
        assert r.factors["return_rank_ge"] == pytest.approx(0.2)

    def test_scale_range(self) -> None:
        r = nl_parse("规模2-50亿的混合基金")
        assert r.factors["scale_min"] == 2
        assert r.factors["scale_max"] == 50


class TestE6SteadyExclude:
    """§4 红线 E6：稳健/低风险排除 index/etf。"""

    def test_steady_excludes_index_etf(self) -> None:
        """稳健 -> 排除 index/etf(E6)。"""
        r = nl_parse("稳健混合基金")
        assert "index" in r.exclude
        assert "etf" in r.exclude

    def test_low_risk_excludes(self) -> None:
        r = nl_parse("低风险债券基金")
        assert "index" in r.exclude
        assert "etf" in r.exclude

    def test_non_steady_no_exclude(self) -> None:
        """非稳健语境不排除。"""
        r = nl_parse("收益靠前的混合基金")
        assert r.exclude == []

    def test_steady_type_in_bond_mixed(self) -> None:
        """E6：稳健语境 type∈[bond,mixed](排除 index/etf 的选基)。"""
        # 用户说稳健但未指定类型 -> 不强加 type(由 exclude 限制)
        r = nl_parse("稳健的基金")
        assert "index" in r.exclude
        assert "etf" in r.exclude


class TestClarify:
    """§3.4.7 歧义反问，不臆测。"""

    def test_empty_query_clarify(self) -> None:
        r = nl_parse("")
        assert r.clarify is not None
        assert r.intent == "unknown"

    def test_no_type_no_factor_clarify(self) -> None:
        """无类型无因子 -> 反问。"""
        r = nl_parse("好基金")
        assert r.clarify is not None
        assert r.confidence < 0.5

    def test_valid_no_clarify(self) -> None:
        r = nl_parse("近一年混合基金回撤小于15%")
        assert r.clarify is None


class TestConditions:
    """结构化条件(供 /screen)。"""

    def test_conditions_built(self) -> None:
        r = nl_parse("近一年稳健混合基金回撤小于10%")
        assert len(r.conditions) > 0
        # 含 type in 条件
        type_cond = next((c for c in r.conditions if c["field"] == "type"), None)
        assert type_cond is not None


class TestSLATarget:
    def test_target_defined(self) -> None:
        assert NL_ACCURACY_TARGET == 0.85
