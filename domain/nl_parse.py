"""NL 选基解析(P1-06b，详设§3.4.7 / TP-02 / DC-004 / CLAUDE.md §4 E6 红线)。

规则兜底解析：自然语言 -> 结构化筛选条件 {type, window, factors, exclude}。
LLM 增强待 C1 key 注入(当前规则层)；歧义返回 clarify(反问)，不臆测(§3.4.7)。

E6 红线(稳健/低风险)：「稳健|低风险」-> ``type ∈ [bond, mixed]``，**排除 index/etf**
(指数年波动~20%、回撤 30-40%，不属低风险)；mixed 用 equity_ratio<0.3 细化。

> 规则基线对齐 ``docs/.../06_NL选基评测/nl_baseline.py``(结构化 100%、对抗 28%)；
> 生产解析器 = LLM + 规则兜底 + 澄清，SLA≥85%(§3.4.7)。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

#: NL 解析准确率门限(§3.4.7)。
NL_ACCURACY_TARGET = 0.85

#: 类型关键词 -> 标准枚举(详设§2.20.2 type)。
TYPE_KW: dict[str, list[str]] = {
    "stock": ["股票", "股票型"],
    "mixed": ["混合", "混合型", "灵活配置"],
    "bond": ["债券", "债券型", "债基"],
    "index": ["指数", "宽基", "行业指数"],
    "etf": ["etf", "场内", "交易所"],
    "qdii": ["qdii", "海外", "美股", "港股"],
    "money": ["货币", "货基", "现金管理"],
}

#: 窗口关键词(详设§3.3.1 默认 3Y)。
WINDOW_KW: list[tuple[str, list[str]]] = [
    ("1y", ["近一年", "近1年", "去年", "1年"]),
    ("3y", ["近三年", "近3年", "三年", "3年"]),
    ("5y", ["近五年", "近5年", "五年", "5年"]),
]

#: 稳健/低风险关键词(E6 红线)。
STEADY_KW = ["稳健", "低风险", "保守", "抗跌", "回撤小", "波动小"]


@dataclass(frozen=True)
class NLResult:
    """NL 解析结果(§2.21.2 POST /api/screen/nl)。

    Attributes:
        intent: 意图(screen/unknown)。
        clarify: 歧义反问(None=无疑义)。
        conditions: 结构化条件 [{field,op,value}]。
        confidence: 置信度(0-1)。
        type_: 基金类型。
        window: 评估窗口。
        factors: 因子条件 {max_drawdown_le, return_rank_ge, ...}。
        exclude: 排除类型(E6: index/etf)。
    """

    intent: str = "screen"
    clarify: str | None = None
    conditions: list[dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.0
    type_: list[str] = field(default_factory=list)
    window: str | None = None
    factors: dict[str, Any] = field(default_factory=dict)
    exclude: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent": self.intent,
            "clarify": self.clarify,
            "conditions": self.conditions,
            "confidence": self.confidence,
            "type": self.type_,
            "window": self.window,
            "factors": self.factors,
            "exclude": self.exclude,
        }


def nl_parse(question: str, *, context: dict[str, Any] | None = None) -> NLResult:
    """NL 规则解析(§3.4.7 / TP-02)。

    Args:
        question: 自然语言查询(如"近一年收益靠前的稳健混合基")。
        context: 上下文(可选,account_id 等)。
    Returns:
        NLResult；歧义 -> clarify(反问)，不臆测。
    """
    _ = context
    if not question or not question.strip():
        return NLResult(intent="unknown", clarify="请输入筛选条件，如'近一年收益靠前的稳健混合基'")

    text = question.strip()

    # 1. 类型检测
    types = _detect_type(text)

    # 2. 窗口检测(默认 3y，§3.3.1)
    window = _detect_window(text)

    # 3. 因子检测
    factors = _detect_factors(text)

    # 4. E6 稳健/低风险：排除 index/etf(§4 红线)
    exclude = _detect_exclude(text, types)

    # 5. 歧义判断：无类型且无因子 -> 反问
    if not types and not factors:
        return NLResult(
            intent="screen",
            clarify="请问您想筛选哪类基金？如'混合型'、'债券型'，或给出具体条件如'回撤小于15%'",
            confidence=0.3,
        )

    # 6. 构造结构化条件(供 /screen 使用)
    conditions = _build_conditions(types, window, factors, exclude)

    # 置信度：规则命中越多越高
    confidence = min(1.0, 0.5 + 0.1 * (len(types) + len(factors) + (1 if window else 0)))

    return NLResult(
        intent="screen",
        clarify=None,
        conditions=conditions,
        confidence=confidence,
        type_=types,
        window=window,
        factors=factors,
        exclude=exclude,
    )


def _detect_type(text: str) -> list[str]:
    """类型检测(对齐 nl_baseline.detect_type)。"""
    types: set[str] = set()
    for t, kws in TYPE_KW.items():
        if any(k in text.lower() for k in kws):
            types.add(t)
    if "etf" in types:
        types.discard("index")  # 宽基ETF 归 etf
    return sorted(types)


def _detect_window(text: str) -> str | None:
    """窗口检测(默认 None，由调用方补 3y)。"""
    for w, kws in WINDOW_KW:
        if any(k in text for k in kws):
            return w
    return None


def _detect_factors(text: str) -> dict[str, Any]:
    """因子检测(回撤/收益排名/规模)。"""
    f: dict[str, Any] = {}
    # 回撤：显式数字 -> max_drawdown_le
    m = re.search(r"回撤[^，。、]*?(\d+(?:\.\d+)?)\s*%", text)
    if m:
        f["max_drawdown_le"] = float(m.group(1)) / 100.0
    elif re.search(r"回撤(小|低|控制好|收敛)|抗跌|稳健|波动小", text):
        f["max_drawdown_le"] = 0.15  # E6 稳健默认
    # 收益排名前 X%
    m = re.search(r"收益排名前\s*(\d+)\s*%", text)
    if m:
        f["return_rank_ge"] = int(m.group(1)) / 100.0
    elif re.search(r"收益(高|靠前|好|排名前)", text):
        f["return_rank_ge"] = 0.2  # 默认前 20%
    # 规模
    m = re.search(r"规模(?:[适中大小区间]*?)(\d+)[-~至](\d+)\s*亿", text)
    if m:
        f["scale_min"] = int(m.group(1))
        f["scale_max"] = int(m.group(2))
    elif "规模适中" in text:
        f["scale_min"] = 2
        f["scale_max"] = 50
    return f


def _detect_exclude(text: str, types: list[str]) -> list[str]:
    """E6 红线：稳健/低风险 -> 排除 index/etf(§4)。

    「稳健|低风险」映射为 type∈[bond,mixed]，排除 index/etf。
    """
    if not any(k in text for k in STEADY_KW):
        return []
    exclude = []
    # 稳健语境下排除 index/etf(E6)
    if "index" not in types:
        exclude.append("index")
    if "etf" not in types:
        exclude.append("etf")
    return exclude


def _build_conditions(
    types: list[str], window: str | None, factors: dict[str, Any], exclude: list[str]
) -> list[dict[str, Any]]:
    """结构化条件 -> /screen filters 格式(§2.21.2)。

    仅生成当前 /screen 可执行条件(type 白名单)；max_drawdown/return_rank 等
    因子条件暂存 NLResult.factors(待 scores 扩展字段后接入)，不臆测生成无效 condition。
    E6：exclude(index/etf) 用 not_in 完整排除(非 != 单值)。
    """
    conds: list[dict[str, Any]] = []
    if types:
        conds.append({"field": "type", "op": "in", "value": types})
    if exclude:
        # E6 红线：完整排除 index/etf(NOT IN，非 != 单值)
        conds.append({"field": "type", "op": "not_in", "value": exclude})
    # max_drawdown/return_rank：funds/scores 表当前无对应字段(D7/批算扩展)，
    # 暂存 NLResult.factors 供前端展示与后续接入，不生成 /screen 无效 condition。
    return conds


__all__: list[str] = ["NL_ACCURACY_TARGET", "NLResult", "nl_parse"]
