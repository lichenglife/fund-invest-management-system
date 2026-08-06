"""NL 选基评测(§3.4.7 / DC-004 / CLAUDE.md §12 评测 oracle)。

复用 ``nl_baseline.py`` 评测口径(strict：clarify 一致性 + type/window/exclude/factors 全匹配)，
对 ``nl_eval_set.json``(100 条 gold) + ``nl_eval_set_adv.json``(60 条对抗)逐条比对。

- 规则地板：``parse_all_rule`` 跑规则层(预期 100 集=100%、对抗=28.3%)；
- LLM 门禁：``parse_all_llm`` 跑生产解析器(``nl_parse_with_llm``)，合并 160 条 strict ≥ 0.85。
"""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, cast

from domain.nl_parse import NLResult, nl_parse_with_llm, rule_parse

#: 因子容差(对齐 nl_baseline.FACTOR_TOL)：ratio 0.02 / scale 1.0 亿。
FACTOR_TOL: dict[str, float] = {"ratio": 0.02, "scale": 1.0}

#: 评测集目录(06_NL选基评测)。
EVAL_DIR = Path("docs/基金评估系统_交付文档/06_NL选基评测")
EVAL_SET_100 = EVAL_DIR / "nl_eval_set.json"
EVAL_SET_ADV = EVAL_DIR / "nl_eval_set_adv.json"


def load_gold(path: str | Path) -> list[dict[str, Any]]:
    """加载评测集 gold(每条 {id, category, question, expect})。"""
    with open(path, encoding="utf-8") as f:
        return cast(list[dict[str, Any]], json.load(f))


def factors_match(got: dict[str, Any], exp: dict[str, Any]) -> tuple[bool, str]:
    """因子匹配(对齐 nl_baseline.factors_match)：键集一致 + 容差内。"""
    gk, ek = set(got), set(exp)
    if gk != ek:
        return False, "key_diff"
    for k in gk:
        gv, ev = got[k], exp[k]
        tol = FACTOR_TOL["scale"] if "scale" in k else FACTOR_TOL["ratio"]
        if abs(float(gv) - float(ev)) > tol:
            return False, f"{k}:{gv}!={ev}"
    return True, ""


def _result_to_cmp(r: NLResult) -> dict[str, Any]:
    """NLResult -> 评测比较面 {clarify,type,window,factors,exclude}。"""
    return {
        "clarify": r.clarify is not None,
        "type": r.type_,
        "window": r.window,
        "factors": r.factors,
        "exclude": r.exclude,
    }


def evaluate(items: list[dict[str, Any]], results: list[NLResult]) -> dict[str, Any]:
    """逐条比对(strict，对齐 nl_baseline.evaluate)。

    Returns:
        ``{total, correct, accuracy, by_category, fails}``。
    """
    total = len(items)
    correct = 0
    by_cat: dict[str, dict[str, int]] = defaultdict(lambda: {"n": 0, "ok": 0})
    fails: list[dict[str, Any]] = []
    for it, got in zip(items, results, strict=True):
        cat = it["category"]
        exp = it["expect"]
        g = _result_to_cmp(got)
        by_cat[cat]["n"] += 1
        # clarify 一致性
        if exp["clarify"] and g["clarify"]:
            correct += 1
            by_cat[cat]["ok"] += 1
            continue
        if exp["clarify"] != g["clarify"]:
            fails.append(
                {"id": it["id"], "q": it["question"], "why": "clarify", "exp": exp, "got": g}
            )
            continue
        # 结构化比较
        type_ok = sorted(exp["type"]) == sorted(g["type"])
        win_ok = exp["window"] == g["window"]
        excl_ok = sorted(exp["exclude"]) == sorted(g["exclude"])
        fac_ok, reason = factors_match(g["factors"], exp["factors"])
        if type_ok and win_ok and excl_ok and fac_ok:
            correct += 1
            by_cat[cat]["ok"] += 1
        else:
            fails.append(
                {
                    "id": it["id"],
                    "q": it["question"],
                    "why": f"type={type_ok},win={win_ok},excl={excl_ok},fac={fac_ok}:{reason}",
                    "exp": exp,
                    "got": g,
                }
            )
    acc = correct / total if total else 0.0
    return {
        "total": total,
        "correct": correct,
        "accuracy": round(acc, 4),
        "by_category": {
            c: {"n": v["n"], "ok": v["ok"], "acc": round(v["ok"] / v["n"], 4) if v["n"] else 0.0}
            for c, v in sorted(by_cat.items())
        },
        "fails": fails,
    }


def parse_all_rule(items: list[dict[str, Any]]) -> list[NLResult]:
    """规则层批量解析(同步)。"""
    return [rule_parse(it["question"]) for it in items]


async def parse_all_llm(items: list[dict[str, Any]]) -> list[NLResult]:
    """LLM 管线批量解析(asyncio.gather 并发，受 LLMClient Semaphore 限流)。"""
    return await asyncio.gather(*(nl_parse_with_llm(it["question"]) for it in items))


async def evaluate_nl_set(path: str | Path, *, use_llm: bool) -> dict[str, Any]:
    """对单个评测集跑解析并评测。

    Args:
        path: 评测集 json 路径。
        use_llm: True=LLM 管线(``nl_parse_with_llm``)；False=规则层。
    """
    items = load_gold(path)
    results = await parse_all_llm(items) if use_llm else parse_all_rule(items)
    return evaluate(items, results)


def combined_strict_acc(rep_100: dict[str, Any], rep_60: dict[str, Any]) -> float:
    """合并 160 条 strict 准确率(DC-004 门禁基准)。"""
    total = rep_100["total"] + rep_60["total"]
    correct = rep_100["correct"] + rep_60["correct"]
    return round(correct / total, 4) if total else 0.0


__all__: list[str] = [
    "EVAL_DIR",
    "EVAL_SET_100",
    "EVAL_SET_ADV",
    "load_gold",
    "factors_match",
    "evaluate",
    "parse_all_rule",
    "parse_all_llm",
    "evaluate_nl_set",
    "combined_strict_acc",
]
