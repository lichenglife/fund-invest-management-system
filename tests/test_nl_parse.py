"""NL 解析单测(P1-06b，详设§3.4.7 / TP-02 / DC-004 / §4 E6 红线)。

覆盖：类型/窗口/因子检测、E6 稳健 TYPE 约束、歧义反问、rule_normalize、LLM 失败兜底。
E6 裁决(§4)：稳健/低风险 -> type∈[bond,mixed](不含 index/etf)，不往 exclude 塞 index/etf。
"""

from __future__ import annotations

import asyncio

import pytest

from domain.nl_parse import (
    NL_ACCURACY_TARGET,
    llm_parse,
    nl_parse,
    nl_parse_with_llm,
    rule_normalize,
)


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


class TestE6TypeConstraint:
    """§4 红线 E6(裁决=TYPE 约束)：稳健/低风险 -> type∈[bond,mixed]，不含 index/etf。

    不往 exclude 塞 index/etf(对齐 §12 评测 oracle：gold.exclude 仅行业)。
    """

    def test_steady_mixed_keeps_mixed(self) -> None:
        """稳健+混合 -> type=[mixed](E6 保留 bond/mixed)。"""
        r = nl_parse("稳健混合基金")
        assert r.type_ == ["mixed"]
        assert "index" not in r.type_
        assert "etf" not in r.type_

    def test_low_risk_bond_keeps_bond(self) -> None:
        r = nl_parse("低风险债券基金")
        assert r.type_ == ["bond"]
        assert "index" not in r.type_

    def test_steady_filters_out_index(self) -> None:
        """稳健+指数(矛盾诉求) -> E6 剔除 index，type 不含 index。"""
        r = nl_parse("稳健的指数基金")
        assert "index" not in r.type_
        assert "etf" not in r.type_

    def test_non_steady_keeps_index(self) -> None:
        """波动小(因子信号，非 E6 触发)+ 指数 -> 保留 index(E6 不过度触发)。"""
        r = nl_parse("波动小的指数基金")
        assert "index" in r.type_

    def test_steady_exclude_is_industry_only(self) -> None:
        """稳健语境 exclude 仅行业(若有否定动词)，无 index/etf。"""
        r = nl_parse("稳健混合，不买军工")
        assert r.exclude == ["军工"]
        assert "index" not in r.exclude
        assert "etf" not in r.exclude


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


class TestRuleNormalize:
    """rule_normalize(提示词稿§6 第3步)：LLM 输出校验/纠偏。"""

    def test_drops_unknown_factor_keys(self) -> None:
        """未知键(beta/dividend)一律丢弃(提示词稿§3)。"""
        obj = {
            "clarify": False,
            "type": ["mixed"],
            "window": "3y",
            "factors": {"max_drawdown_le": 0.15, "beta": 1.2, "dividend": 0.3},
            "exclude": [],
        }
        n = rule_normalize(obj)
        assert set(n["factors"]) == {"max_drawdown_le"}
        assert n["factors"]["max_drawdown_le"] == 0.15

    def test_clamps_ratio_to_unit(self) -> None:
        """ratio 类越界(>1)钳制到 1.0。"""
        n = rule_normalize(
            {
                "clarify": False,
                "type": [],
                "window": None,
                "factors": {"max_drawdown_le": 1.5, "return_rank_ge": -0.1},
                "exclude": [],
            }
        )
        assert n["factors"]["max_drawdown_le"] == 1.0
        assert n["factors"]["return_rank_ge"] == 0.0

    def test_filters_invalid_type_enum(self) -> None:
        n = rule_normalize(
            {
                "clarify": False,
                "type": ["mixed", "foobar", "bond"],
                "window": None,
                "factors": {},
                "exclude": [],
            }
        )
        assert sorted(n["type"]) == ["bond", "mixed"]

    def test_invalid_window_becomes_none(self) -> None:
        n = rule_normalize(
            {"clarify": False, "type": [], "window": "10y", "factors": {}, "exclude": []}
        )
        assert n["window"] is None

    def test_clarify_passthrough(self) -> None:
        n = rule_normalize(
            {
                "clarify": True,
                "clarify_question": "补充类型？",
                "type": [],
                "window": None,
                "factors": {},
                "exclude": [],
            }
        )
        assert n["clarify"] is True
        assert n["clarify_question"] == "补充类型？"

    def test_non_dict_returns_clarify(self) -> None:
        n = rule_normalize("not a dict")  # type: ignore[arg-type]
        assert n["clarify"] is True


class TestLLMFallback:
    """LLM 失败/无 key -> 规则兜底(§2.15 降级)，source 可追溯。"""

    def test_fast_path_structured_returns_rule(self) -> None:
        """规则高置信结构化句 -> fast-path 直接返回规则(省 LLM)。"""
        r = asyncio.run(nl_parse_with_llm("近三年混合基金里回撤小于15%、收益排名前20%的"))
        assert r.source == "rule"
        assert r.clarify is None
        assert r.confidence >= 0.85

    def test_llm_unavailable_falls_back_to_rule(self) -> None:
        """无 LLM_API_KEY 时，garbled 句走规则兜底(source=rule)。"""
        r = asyncio.run(nl_parse_with_llm("近san年huode高的混和基"))
        assert r.source == "rule"

    def test_llm_parse_returns_none_when_disabled(self) -> None:
        """无 key -> LLMClient 不可用 -> llm_parse 返回 None。"""
        r = asyncio.run(llm_parse("稳健混合基金"))
        assert r is None


class TestSLATarget:
    def test_target_defined(self) -> None:
        assert NL_ACCURACY_TARGET == 0.85
