"""NL 选基解析(P1-06b，详设§3.4.7 / TP-02 / DC-004 / CLAUDE.md §4 E6 红线)。

生产解析器 = 规则兜底 + LLM 语义解析 + 歧义反问(§3.4.7 / 提示词稿§6)：
  规则先判(fast-path, conf≥0.85 直接返回省 LLM) -> 否则 LLM(限流) ->
  rule_normalize 校验/纠偏 -> conf<0.60 转规则兜底/反问。``source`` 可追溯(DC-004)。

规则层**忠实对齐** ``docs/.../06_NL选基评测/nl_baseline.py``(结构化 100%、对抗 28%)：
  TYPE_KW/WINDOW_KW/SECTORS/NEG_VERB/detect_*  与 baseline 同口径，保证 100 集可复算。

E6 红线(§4，裁决=TYPE 约束)：「稳健|低风险」-> 结构化结果 ``type ∈ [bond, mixed]``
(从检测到的 type 中剔除 index/etf 等)，**不**往 exclude 塞 index/etf--与 §12 评测 oracle
(gold.exclude 仅行业)一致；稳健 query 的 type 永不含 index/etf。

> LLM 增强后合并 160 条 strict acc ≥ 0.85(NL_ACCURACY_TARGET)。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

#: NL 解析准确率门限(§3.4.7 / DC-004)。
NL_ACCURACY_TARGET = 0.85

#: 置信度阈值(TP-02 §3.2)：≥此值直接执行；<0.60 视为歧义/失败。
CONFIRM_THRESHOLD = 0.85
CLARIFY_THRESHOLD = 0.60

#: 类型关键词 -> 标准枚举(对齐 nl_baseline.TYPE_KW / 详设§2.20.2)。
TYPE_KW: dict[str, list[str]] = {
    "etf": ["ETF", "场内"],
    "index": ["指数", "宽基"],
    "stock": ["股票", "主动股票", "股票型"],
    "mixed": ["混合", "股混", "主动混合", "混合偏股"],
    "bond": ["债券", "债基", "纯债", "二级债", "债券型"],
    "qdii": ["QDII", "海外"],
    "money": ["货币", "货基"],
}

#: 类型白名单(LLM 输出校验，提示词稿§3 枚举约束)。
VALID_TYPES: set[str] = {"stock", "mixed", "bond", "index", "etf", "qdii", "money"}
#: 窗口白名单(提示词稿§3 / 对齐 nl_baseline.WINDOW_KW)。
VALID_WINDOWS: set[str | None] = {"1y", "3y", "5y", "ytd", "since", None}
#: factors 合法键(提示词稿§3；未知键一律丢弃)。
VALID_FACTOR_KEYS: set[str] = {
    "max_drawdown_le",
    "return_rank_ge",
    "annual_return_ge",
    "volatility_le",
    "scale_min",
    "scale_max",
    "sharpe_ge",
}

#: 窗口关键词(对齐 nl_baseline.WINDOW_KW，详设§3.3.1 默认 3Y)。
WINDOW_KW: list[tuple[str, list[str]]] = [
    ("ytd", ["今年以来", "年内", "今年"]),
    ("since", ["成立以来", "长期持有", "长期业绩", "长期表现", "长期看"]),
    ("5y", ["近五年", "五年"]),
    ("3y", ["近三年", "三年"]),
    ("1y", ["近一年", "一年"]),
]

#: 行业/主题词(长词优先，对齐 nl_baseline.SECTORS)。
SECTORS: list[str] = [
    "新能源车",
    "新能源",
    "美股科技",
    "半导体",
    "房地产",
    "地产",
    "军工",
    "医药",
    "白酒",
    "可转债",
    "城投",
    "互联网",
    "港股通",
    "原油",
    "黄金",
    "券商",
    "保险",
    "金融",
]
#: 否定动词(对齐 nl_baseline.NEG_VERBS)。
NEG_VERBS: list[str] = ["不要", "别碰", "别买", "不买", "剔除", "避开"]

#: E6 红线触发词(§4：仅「稳健|低风险」触发 TYPE 约束；波动小/回撤小/抗跌属因子信号，不触发)。
E6_TRIGGER: set[str] = {"稳健", "低风险"}
#: E6 允许类型(稳健/低风险 -> type∈[bond, mixed])。
E6_ALLOWED: set[str] = {"bond", "mixed"}


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
        exclude: 排除行业/主题(对齐 nl_baseline；E6 index/etf 改由 type 约束)。
        source: 解析来源(DC-004 可追溯) ``rule``/``llm``。
    """

    intent: str = "screen"
    clarify: str | None = None
    conditions: list[dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.0
    type_: list[str] = field(default_factory=list)
    window: str | None = None
    factors: dict[str, Any] = field(default_factory=dict)
    exclude: list[str] = field(default_factory=list)
    source: str = "rule"

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
            "source": self.source,
        }


# ---------------------------------------------------------------------------
# 规则层(对齐 nl_baseline.py)
# ---------------------------------------------------------------------------


def _nums(text: str) -> list[float]:
    return [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)", text)]


def _detect_type(text: str) -> list[str]:
    """类型检测(对齐 nl_baseline.detect_type)。"""
    types: set[str] = set()
    for t, kws in TYPE_KW.items():
        if any(k in text for k in kws):
            types.add(t)
    if "etf" in types:
        types.discard("index")  # 宽基ETF/指数ETF 只归 etf
    return sorted(types)


def _detect_window(text: str) -> str | None:
    """窗口检测(对齐 nl_baseline.detect_window)。"""
    for w, kws in WINDOW_KW:
        if any(k in text for k in kws):
            return w
    return None


def _detect_factors(text: str) -> dict[str, Any]:
    """因子检测(对齐 nl_baseline.detect_factors)。"""
    f: dict[str, Any] = {}
    # 回撤：显式数字 -> max_drawdown_le；否则"小/低/控制好/收敛/抗跌/稳健" -> 默认 0.15
    m = re.search(r"回撤[^，。、]*?(\d+(?:\.\d+)?)\s*%", text)
    if m:
        f["max_drawdown_le"] = float(m.group(1)) / 100.0
    elif re.search(r"回撤(小|低|控制好|收敛)|抗跌|稳健", text):
        f["max_drawdown_le"] = 0.15
    # 收益排名前 X%
    m = re.search(r"收益排名前\s*(\d+)\s*%", text)
    if m:
        f["return_rank_ge"] = int(m.group(1)) / 100.0
    # 年化收益 X% 以上
    m = re.search(r"年化收益\s*(\d+(?:\.\d+)?)\s*%以上", text)
    if m:
        f["annual_return_ge"] = float(m.group(1)) / 100.0
    # 收益稳定 / 走势平稳 / 平稳 / 稳定 -> 波动默认 0.10
    if re.search(r"收益稳定|走势平稳|平稳|稳定", text):
        f["volatility_le"] = 0.10
    # 收益高/好/靠前/不错/累计收益高/长期业绩好(独立于"稳定"分支)
    if re.search(r"收益(高|好|靠前|不错)|累计收益高|长期业绩好|表现不错", text):
        f["return_rank_ge"] = f.get("return_rank_ge", 0.20)
    # 波动小/低/可控
    if re.search(r"波动(小|低|可控)", text):
        f["volatility_le"] = 0.10
    # 规模
    if "规模适中" in text:
        f["scale_min"], f["scale_max"] = 2.0, 50.0
    elif re.search(r"规模(大|百亿以上)|百亿", text):
        f["scale_min"] = 50.0
    elif re.search(r"规模小|迷你|5亿内", text):
        f["scale_max"] = 5.0
    m = re.search(r"规模在?\s*(\d+(?:\.\d+)?)\s*[-到]\s*(\d+(?:\.\d+)?)\s*亿", text)
    if m:
        f["scale_min"], f["scale_max"] = float(m.group(1)), float(m.group(2))
    # 夏普
    m = re.search(r"夏普[^，。、%]*?(\d+(?:\.\d+)?)", text)
    if m:
        f["sharpe_ge"] = float(m.group(1))
    elif "夏普高" in text:
        f["sharpe_ge"] = 1.0
    return f


def _detect_exclude(text: str) -> list[str]:
    """行业/主题排除(对齐 nl_baseline.detect_exclude)。

    否定动词 + 行业词 -> exclude；长短去重(短词是已匹配长词子串则丢弃)。
    E6 的 index/etf 改由 type 约束(§4 裁决)，不入 exclude。
    """
    if not any(v in text for v in NEG_VERBS):
        return []
    ex = [s for s in SECTORS if s in text]
    # 长短去重：若某词是另一已匹配词子串(如 新能源⊂新能源车、地产⊂房地产)，丢弃短词
    ex = [s for s in ex if not any(s != t and s in t for t in ex)]
    return ex


def _apply_e6(text: str, types: list[str]) -> list[str]:
    """E6 红线(§4 裁决=TYPE 约束)：稳健/低风险 -> type∈[bond, mixed]。

    从检测到的 type 中剔除 index/etf 等非低风险类型；稳健 query 永不返 index/etf。
    """
    if not any(k in text for k in E6_TRIGGER):
        return types
    return [t for t in types if t in E6_ALLOWED]


def rule_parse(question: str, *, context: dict[str, Any] | None = None) -> NLResult:
    """规则兜底解析(§3.4.7 / TP-02 §3.3，对齐 nl_baseline.nl_parse)。

    Args:
        question: 自然语言查询(如"近一年收益靠前的稳健混合基")。
        context: 上下文(可选,account_id 等)。
    Returns:
        NLResult(source="rule")；歧义 -> clarify(反问)，不臆测。
    """
    _ = context
    if not question or not question.strip():
        return NLResult(intent="unknown", clarify="请输入筛选条件，如'近一年收益靠前的稳健混合基'")

    text = question.strip()
    types = _apply_e6(text, _detect_type(text))
    window = _detect_window(text)
    factors = _detect_factors(text)
    exclude = _detect_exclude(text)
    has_num = bool(_nums(text))

    # 歧义判断(对齐 nl_baseline)：无类型 + 无区间 + 无数字阈值 -> clarify
    if (not types) and (window is None) and (not has_num):
        return NLResult(
            intent="screen",
            clarify="请问您想筛选哪类基金？如'混合型'、'债券型'，或给出具体条件如'回撤小于15%'",
            confidence=0.3,
            source="rule",
        )

    conditions = _build_conditions(types, factors, exclude)
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
        source="rule",
    )


def nl_parse(question: str, *, context: dict[str, Any] | None = None) -> NLResult:
    """NL 规则解析(同步, §3.4.7 / TP-02)。

    规则兜底层；LLM 增强见 :func:`nl_parse_with_llm`(端点在 key 注入时调用)。
    保留同步签名以兼容现有调用与单测。

    Args:
        question: 自然语言查询。
        context: 上下文(可选,account_id 等)。
    Returns:
        NLResult；歧义 -> clarify(反问)，不臆测。
    """
    return rule_parse(question, context=context)


def _build_conditions(
    types: list[str], factors: dict[str, Any], exclude: list[str]
) -> list[dict[str, Any]]:
    """结构化条件 -> /screen filters 格式(§2.21.2)。

    仅生成当前 /screen 可执行条件(type 白名单)；max_drawdown/return_rank 等因子条件
    暂存 NLResult.factors(待 scores 扩展字段后接入)；行业 exclude 暂存 NLResult.exclude
    (无对应 /screen 字段)，均不臆测生成无效 condition。
    """
    _ = factors, exclude
    conds: list[dict[str, Any]] = []
    if types:
        conds.append({"field": "type", "op": "in", "value": types})
    return conds


# ---------------------------------------------------------------------------
# LLM 层(rule_normalize + llm_parse + 编排器，TP-02 §3.2/§3.3 / 提示词稿§6)
# ---------------------------------------------------------------------------


def rule_normalize(obj: dict[str, Any]) -> dict[str, Any]:
    """校验/归一 LLM JSON 输出(提示词稿§6 第3步 / §3 枚举约束)。

    强制枚举白名单、丢弃未知 factors 键、钳制数值越界，防止模型漂移。
    """
    if not isinstance(obj, dict):
        return {
            "clarify": True,
            "clarify_question": "解析异常，请补充类型/区间/阈值",
            "type": [],
            "window": None,
            "factors": {},
            "exclude": [],
        }

    clarify = bool(obj.get("clarify", False))
    clarify_q = obj.get("clarify_question")
    if clarify_q is not None:
        clarify_q = str(clarify_q)

    raw_types = obj.get("type") or []
    types = sorted({t for t in raw_types if isinstance(t, str) and t in VALID_TYPES})

    win = obj.get("window")
    window = win if win in VALID_WINDOWS else None

    raw_factors = obj.get("factors") or {}
    factors: dict[str, Any] = {}
    if isinstance(raw_factors, dict):
        for k in VALID_FACTOR_KEYS:
            if k in raw_factors:
                v = _clamp_factor(k, raw_factors[k])
                if v is not None:
                    factors[k] = v

    raw_excl = obj.get("exclude") or []
    exclude = [str(e) for e in raw_excl if isinstance(e, str) and e]

    return {
        "clarify": clarify,
        "clarify_question": clarify_q,
        "type": types,
        "window": window,
        "factors": factors,
        "exclude": exclude,
    }


def _clamp_factor(key: str, val: Any) -> float | None:
    """钳制因子数值到合法区间(提示词稿§3)。"""
    try:
        v = float(val)
    except (TypeError, ValueError):
        return None
    if key in ("scale_min", "scale_max"):
        return max(0.0, v)  # 亿元，非负
    if key == "sharpe_ge":
        return v  # 夏普可为负
    return min(1.0, max(0.0, v))  # ratio 类 [0,1]


async def llm_parse(question: str, *, context: dict[str, Any] | None = None) -> NLResult | None:
    """LLM 语义解析(§3.4.7 / 提示词稿§6 第2步)。

    调 :class:`LLMClient` -> ``rule_normalize`` -> NLResult。失败/超时返回 None(由编排器兜底)。
    E6 兜底(§4)：即便 LLM 漏判稳健，仍按 query 复检并强制 type∈[bond,mixed]。
    """
    _ = context
    from infra.external.llm_client import LLMClient  # 延迟导入避免无 key 时构造失败

    client = LLMClient()
    if not client.is_enabled:
        return None
    raw = await client.complete_json(question)
    if raw is None:
        return None
    obj = rule_normalize(raw)
    text = question.strip()
    # E6 强制(§4 红线)：稳健/低风险 -> type∈[bond,mixed]
    types = _apply_e6(text, obj["type"])
    if obj["clarify"]:
        return NLResult(
            intent="screen",
            clarify=obj["clarify_question"] or "请补充基金类型与查看区间",
            confidence=0.0,
            type_=types,
            window=obj["window"],
            factors=obj["factors"],
            exclude=obj["exclude"],
            source="llm",
        )
    conditions = _build_conditions(types, obj["factors"], obj["exclude"])
    return NLResult(
        intent="screen",
        clarify=None,
        conditions=conditions,
        confidence=0.9,
        type_=types,
        window=obj["window"],
        factors=obj["factors"],
        exclude=obj["exclude"],
        source="llm",
    )


async def nl_parse_with_llm(
    question: str,
    *,
    context: dict[str, Any] | None = None,
    history: list[dict[str, str]] | None = None,
) -> NLResult:
    """生产解析器编排(§3.4.7 / TP-02 §3.2 / 提示词稿§6)。

    1) 规则先判：conf≥CONFIRM_THRESHOLD 且非 clarify -> 直接返回(省 LLM 成本)；
    2) LLM(限流) -> normalize；成功且非 clarify -> 返回(source=llm)；
    3) LLM 失败/低置信 -> 规则兜底(source=rule)。

    Args:
        question: 自然语言查询。
        context: 上下文(account_id 等)。
        history: 多轮澄清历史(首版单句解析，v1.1 增强跨句指代，提示词稿§11.2)。
    """
    _ = history  # v1.1：透传至 prompt 构建多轮上下文
    rule = rule_parse(question, context=context)
    if rule.confidence >= CONFIRM_THRESHOLD and not rule.clarify:
        return rule

    llm = await llm_parse(question, context=context)
    if llm is not None:
        return llm  # 含 clarify 与结构化两种(source=llm)
    # LLM 失败 -> 规则兜底(§2.15 降级)
    return rule


__all__: list[str] = [
    "NL_ACCURACY_TARGET",
    "CONFIRM_THRESHOLD",
    "CLARIFY_THRESHOLD",
    "NLResult",
    "rule_parse",
    "nl_parse",
    "rule_normalize",
    "llm_parse",
    "nl_parse_with_llm",
]
