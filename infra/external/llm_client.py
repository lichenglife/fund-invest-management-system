"""LLM 客户端(TP-02 §3.4.8 限流 / ``07_LLM提示词``设计稿 §4-§6/§9 / DC-004)。

DeepSeek OpenAI 兼容 /chat/completions + JSON Mode，把用户自然语言映射为结构化
筛选条件 JSON。**只做语义->结构映射**，不荐基、不输出买卖建议(提示词稿 §2.5)。

> 选型说明：CLAUDE.md §2 AI 栈列 LangChain+Chroma，属 Phase 3 AI 助手 RAG(TP-06)；
> 本 P1-06b NL 解析按 ``07_LLM提示词``设计稿 §6/§9 将 LLM 视为 HTTP/JSON-mode 调用
> (``llm_chat(json_mode=True, timeout=3.0)``)，TP 级权威设计优先(CLAUDE.md 冲突裁决)，
> 故用 httpx 直连；LangChain 留 Phase 3。

降级(§2.15 / §8.5)：超时/429/JSON 非法 -> 返回 None，由 domain.nl_parse 规则兜底，不抛。
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, cast

import httpx

from config.settings import get_settings

logger = logging.getLogger(__name__)

#: DeepSeek/OpenAI 兼容 chat completions 路径。
_CHAT_PATH = "/chat/completions"

#: system prompt(取自 ``07_LLM提示词``设计稿 §4，原文固化，禁止漂移)。
SYSTEM_PROMPT = """你是一个基金筛选系统的「语义解析器」，负责把用户的自然语言需求转换为结构化筛选条件 JSON。
你不做基金推荐、不输出任何基金代码、不给出任何买卖建议。

# 输出要求
- 仅输出一个 JSON 对象，不要任何解释或前后缀文字。
- 字段必须严格遵循下方「输出结构」。

# 输出结构
{
  "clarify": bool,                 // 信息不足需反问时为 true
  "clarify_question": string|null, // clarify=true 时给用户的具体反问；否则 null
  "type": string[],                // 取值: stock/mixed/bond/index/etf/qdii/money；不确定可空
  "window": string|null,           // 取值: 1y/3y/5y/ytd/since；无区间则 null
  "factors": object,               // 仅含以下键，无则空对象：
                                   //   max_drawdown_le(回撤上限,小数) return_rank_ge(收益排名前X%,小数)
                                   //   annual_return_ge(年化收益下限,小数) volatility_le(波动率上限,小数)
                                   //   scale_min/scale_max(规模,亿元) sharpe_ge(夏普下限,小数)
  "exclude": string[]              // 用户明确不要的行业/主题
}

# 归一规则（重要）
1. 中文/汉字数字 -> 阿拉伯数字：十几个点->0.15；百分之二十->0.20；两成->0.20；五个点->0.05；两三个亿->scale_min=2,scale_max=3。
2. 错别字/谐音归一：混和->混合；收溢->收益；白九->白酒；股票鸡->股票基；波懂->波动；规莫->规模；忆->亿；考前->靠前；一念->一年；san年->三年；huode->获得。
3. 中英混用：low risk->低波动低回撤(max_drawdown_le≈0.15)；sharpe 高->sharpe_ge=1.0；volatile->volatility_le=0.10；high return/top 20%->return_rank_ge=0.20；long term->window=since。
4. 俚语映射：别坐过山车/躺赢/别一把亏光/稳稳/血本无归->低波动低回撤(volatility_le≈0.10 或 max_drawdown_le≈0.15)；跑赢余额宝两三倍->annual_return_ge≈0.06（标注为估算）。
5. 否定词（不要/别碰/剔除/避开/不买）+ 行业 -> 放入 exclude。
6. 跨句指代（"跟上面那个差不多""就要昨天聊那种"）无法从本句解析 -> clarify=true，反问请用户补充类型/区间/阈值。

# 反问原则
- 当 type 为空 且 window 为 null 且 无具体数字阈值 时，必须 clarify=true。
- 反问要具体、可选项化（如"您偏向哪类基金？看多长区间？"），不要泛泛而问。

# 禁止
- 禁止编造基金代码、名称、收益数字。
- 禁止输出 JSON 以外的文字。
- 禁止对缺失维度填默认值（如"规模适中"才可填 scale 2-50，纯"好基金"不可填）。
"""

#: few-shot 示例(取自 ``07_LLM提示词``设计稿 §5，覆盖 5 类失败模式 + 反问 + 跨句指代)。
#: 以 messages 形式注入；每例 = (user, assistant_json)。
FEW_SHOT: list[tuple[str, str]] = [
    # 示例 1 - 标准结构化(对照基线 100%)
    (
        "近三年混合基金里回撤小于15%、收益排名前20%的",
        '{"clarify":false,"clarify_question":null,"type":["mixed"],"window":"3y",'
        '"factors":{"max_drawdown_le":0.15,"return_rank_ge":0.20},"exclude":[]}',
    ),
    # 示例 2 - 错别字/谐音(对抗 M)
    (
        "近san年huode高、回撤小的混和基",
        '{"clarify":false,"clarify_question":null,"type":["mixed"],"window":"3y",'
        '"factors":{"return_rank_ge":0.20,"max_drawdown_le":0.15},"exclude":[]}',
    ),
    (
        "想买点主动混和，别碰白九",
        '{"clarify":false,"clarify_question":null,"type":["mixed"],"window":null,'
        '"factors":{},"exclude":["白酒"]}',
    ),
    # 示例 3 - 中英混用(对抗 N)
    (
        "sharpe 高一点，回撤小的股票",
        '{"clarify":false,"clarify_question":null,"type":["stock"],"window":null,'
        '"factors":{"sharpe_ge":1.0,"max_drawdown_le":0.15},"exclude":[]}',
    ),
    (
        "ETF 别太 volatile，规模大些",
        '{"clarify":false,"clarify_question":null,"type":["etf"],"window":null,'
        '"factors":{"volatility_le":0.10,"scale_min":50.0},"exclude":[]}',
    ),
    # 示例 4 - 汉字/中文数字(对抗 O)
    (
        "回撤十几个点以内的混合",
        '{"clarify":false,"clarify_question":null,"type":["mixed"],"window":null,'
        '"factors":{"max_drawdown_le":0.15},"exclude":[]}',
    ),
    (
        "收益前百分之二十的混合",
        '{"clarify":false,"clarify_question":null,"type":["mixed"],"window":null,'
        '"factors":{"return_rank_ge":0.20},"exclude":[]}',
    ),
    (
        "规模两三个亿到五十亿的混合",
        '{"clarify":false,"clarify_question":null,"type":["mixed"],"window":null,'
        '"factors":{"scale_min":2.0,"scale_max":50.0},"exclude":[]}',
    ),
    # 示例 5 - 俚语(对抗 K)
    (
        "别坐过山车，稳稳的债基",
        '{"clarify":false,"clarify_question":null,"type":["bond"],"window":null,'
        '"factors":{"volatility_le":0.10},"exclude":[]}',
    ),
    (
        "近一年别太刺激、能跑赢余额宝两三倍、别买新能源的混合",
        '{"clarify":false,"clarify_question":null,"type":["mixed"],"window":"1y",'
        '"factors":{"annual_return_ge":0.06},"exclude":["新能源"]}',
    ),
    # 示例 6 - 歧义反问(对抗 E/L)
    (
        "想找个好一点的基金",
        '{"clarify":true,"clarify_question":"您偏向哪类基金（混合/股票/债券/指数等）？'
        '想看多长区间（近一年/三年/成立以来）的表现？","type":[],"window":null,'
        '"factors":{},"exclude":[]}',
    ),
    (
        "跟上面那个差不多，但别碰白酒",
        '{"clarify":true,"clarify_question":"本轮为单句解析，无法获知『上面那个』的具体类型与区间，'
        '请补充：类型？区间？以及回撤/收益等阈值？","type":[],"window":null,'
        '"factors":{},"exclude":["白酒"]}',
    ),
    # 示例 7 - 组合自由表述(对抗 P)
    (
        "近三年涨得多跌得少、别买军工和半导体的股混",
        '{"clarify":false,"clarify_question":null,"type":["mixed"],"window":"3y",'
        '"factors":{"return_rank_ge":0.20,"max_drawdown_le":0.15},"exclude":["军工","半导体"]}',
    ),
]


def _build_messages(user_query: str) -> list[dict[str, str]]:
    """组装 messages：system + few-shot(交替 user/assistant) + 用户问句(提示词稿 §5)。"""
    msgs: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for u, a in FEW_SHOT:
        msgs.append({"role": "user", "content": u})
        msgs.append({"role": "assistant", "content": a})
    msgs.append({"role": "user", "content": user_query})
    return msgs


class LLMClient:
    """DeepSeek/OpenAI 兼容 LLM 客户端(§3.4.8 限流 + §2.15 降级)。

    并发经 ``asyncio.Semaphore``(settings.llm_max_concurrency)限流防 429；
    超时 ``settings.llm_timeout``；任一失败返回 None 由上层规则兜底。
    """

    def __init__(self) -> None:
        s = get_settings()
        self._api_key = s.llm_api_key
        self._base_url = s.llm_base_url.rstrip("/")
        self._model = s.llm_model
        self._timeout = s.llm_timeout
        self._sem = asyncio.Semaphore(s.llm_max_concurrency)

    @property
    def is_enabled(self) -> bool:
        """LLM 是否可用(key 已注入)；空 key -> 禁用，走纯规则。"""
        return bool(self._api_key)

    async def complete_json(self, user_query: str) -> dict[str, Any] | None:
        """调用 LLM 返回结构化 JSON dict；失败/超时/非法 -> None(降级，§2.15)。

        Args:
            user_query: 用户自然语言问句(视为不可信输入，提示词稿 §7 防注入)。
        Returns:
            解析后的 JSON dict 或 None。
        """
        if not self.is_enabled:
            return None
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        body = {
            "model": self._model,
            "messages": _build_messages(user_query),
            "response_format": {"type": "json_object"},
            "temperature": 0.0,
            "max_tokens": 512,
        }
        url = f"{self._base_url}{_CHAT_PATH}"
        async with self._sem:
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as cli:
                    resp = await cli.post(url, headers=headers, json=body)
            except (httpx.TimeoutException, httpx.HTTPError) as exc:
                logger.warning("LLM 调用失败(降级规则兜底): %s", exc)
                return None
        if resp.status_code != 200:
            logger.warning("LLM 非 200(status=%s, 降级规则兜底)", resp.status_code)
            return None
        try:
            raw = resp.json()["choices"][0]["message"]["content"]
            parsed = json.loads(raw)
        except (KeyError, ValueError, json.JSONDecodeError) as exc:
            logger.warning("LLM 响应非法 JSON(降级规则兜底): %s", exc)
            return None
        if not isinstance(parsed, dict):
            logger.warning("LLM 响应非 JSON 对象(降级规则兜底): %r", type(parsed).__name__)
            return None
        return cast(dict[str, Any], parsed)


__all__: list[str] = ["LLMClient", "SYSTEM_PROMPT", "FEW_SHOT"]
