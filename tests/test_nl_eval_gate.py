"""NL 评测门禁(P1-06b / DC-004 / CLAUDE.md §12 评测 oracle)。

- ``test_rule_floor_100set``：规则层在 100 条 gold 上 strict acc=1.0(对齐 nl_baseline 报告)；
- ``test_rule_floor_adv_documented``：规则层在 60 条对抗上 strict acc=0.2833(地板，<0.85 证明需 LLM)；
- ``test_llm_gate_160``：LLM 管线合并 160 条 strict acc≥0.85(真门禁，需 LLM_API_KEY)。

> 规则地板测试始终跑(无外部依赖)；LLM 门禁 ``skipif`` 无 key 时跳过并告警。
"""

from __future__ import annotations

import asyncio

import pytest

from config.settings import get_settings
from domain.nl_eval import (
    EVAL_SET_100,
    EVAL_SET_ADV,
    combined_strict_acc,
    evaluate_nl_set,
)
from domain.nl_parse import NL_ACCURACY_TARGET


def test_rule_floor_100set() -> None:
    """规则层 100 集 strict=1.0(对齐 nl_baseline 报告；回归保护)。"""
    rep = asyncio.run(evaluate_nl_set(EVAL_SET_100, use_llm=False))
    assert rep["accuracy"] == 1.0, f"规则地板 100 集应为 100%，实际 {rep['accuracy']}"


def test_rule_floor_adv_documented() -> None:
    """规则层 60 对抗 strict=0.2833(地板；<0.85 证明需 LLM 增强)。"""
    rep = asyncio.run(evaluate_nl_set(EVAL_SET_ADV, use_llm=False))
    assert rep["accuracy"] == pytest.approx(
        0.2833, abs=0.01
    ), f"规则对抗地板应为 0.2833，实际 {rep['accuracy']}"
    assert rep["accuracy"] < NL_ACCURACY_TARGET  # 证明规则单独不达门禁


def test_rule_combined_below_gate() -> None:
    """规则层合并 160 条 < 0.85(门禁需 LLM；回归保护)。"""
    r100 = asyncio.run(evaluate_nl_set(EVAL_SET_100, use_llm=False))
    r60 = asyncio.run(evaluate_nl_set(EVAL_SET_ADV, use_llm=False))
    combined = combined_strict_acc(r100, r60)
    assert combined < NL_ACCURACY_TARGET, f"规则合并应 <0.85，实际 {combined}"


@pytest.mark.skipif(
    not get_settings().llm_api_key,
    reason="需 LLM_API_KEY 注入(DC-004 门禁)；无 key 时跳过，规则地板见上",
)
def test_llm_gate_160() -> None:
    """LLM 管线合并 160 条 strict acc≥0.85(DC-004 真门禁)。"""
    r100 = asyncio.run(evaluate_nl_set(EVAL_SET_100, use_llm=True))
    r60 = asyncio.run(evaluate_nl_set(EVAL_SET_ADV, use_llm=True))
    combined = combined_strict_acc(r100, r60)
    assert combined >= NL_ACCURACY_TARGET, (
        f"LLM 合并 160 条未达门禁 ≥{NL_ACCURACY_TARGET}，实际 {combined}；"
        f"100集={r100['accuracy']} 对抗={r60['accuracy']}"
    )
