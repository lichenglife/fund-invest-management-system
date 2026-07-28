# 技术方案 TP-02 · 智能筛选器之自然语言选基（NL 解析管线）

> **对应模块**：§3.4 智能筛选器（BRD 模块三 FR-11~14，DC-004）
> **目标**：将 NL 选基从「LLM + 限流」描述落地为**可直接编码**的条件词表、澄清状态机、规则兜底与 SLA 评测内嵌方案。
> **前置依赖**：详细设计 §2.21/§3.4/§3.4.8、07_LLM提示词设计稿、06_NL选基评测（160 条语料）

---

## 1. 范围与目标

- 输入：自然语言 query + `context`（account_id 等）。
- 输出：结构化 `intent`（screen / compare / explain）+ `conditions`（字段条件数组）+ `confidence` + `clarify`（歧义反问）。
- 硬指标：`NL_ACCURACY_TARGET = 0.85`（基于 100+60 条标注集），未达标走规则兜底 + 人工复核，**禁止低置信度臆测**（§3.4.7）。

---

## 2. 现有设计缺口

| 缺口 | 说明 | 本方案处置 |
|------|------|-----------|
| 条件词表未全集化 | §2.21 仅示例部分 field/op | §3.1 给出完整枚举与值类型 |
| 澄清状态机未定义 | §3.4.2 仅画"歧义→反问" | §3.2 多轮澄清状态机 |
| 规则兜底未落地 | 仅提"规则兜底"无实现 | §3.3 正则/关键词兜底引擎 |
| SLA 评测未内嵌 | 评测集独立于解析路径 | §3.4 评测如何驱动兜底决策 |

---

## 3. 关键算法与代码逻辑

### 3.1 条件词表（闭环 S4 字段级契约补全）

```python
# field 全集（对齐 §3.4 / BRD BR-3.1）
FIELD = {
    "type":      "基金类型",        # 枚举: stock/mixed/bond/index/etf/lof/qdii/money/fof
    "score":     "综合评分",        # 0-100
    "ret":       "年化收益(%)",
    "risk":      "最大回撤(%)",     # 注意: 业务语义"回撤小"= risk 数值小
    "sharpe":    "夏普比率",
    "scale":     "规模(亿)",
    "manager":   "经理任职回报(%)",
    "theme":     "主题/行业",       # 自由词 → 主题映射表
    "window":    "区间",            # 1y/3y/5y/max
}
OP = {"=", "!=", ">", ">=", "<", "<=", "in", "not_in", "between"}
# 值类型: 数值 / 枚举 / 区间(between: [lo,hi]) / 主题词
Condition = {"field": str, "op": str, "value": Any, "neg": bool}  # neg=True 表示"非/排除"
SortSpec = {"field": "composite|ret|risk|sharpe", "order": "asc|desc"}
Intent = {"intent": "screen|compare|explain",
          "conditions": [Condition], "sort": SortSpec,
          "confidence": float, "clarify": Optional[str],
          "source": "llm|rule"}     # 来源可追溯(DC-004)
```

### 3.2 澄清状态机（多轮）

```python
CLARIFY_THRESHOLD = 0.60     # <此值视为歧义/失败
CONFIRM_THRESHOLD = 0.85     # ≥此值直接执行

def parse_nl(query, ctx, history=None) -> Intent:
    prompt = build_prompt(query, ctx, history)        # 07_LLM提示词: system+few-shot+JSON契约
    raw = await llm_complete(prompt)                  # 受 §3.4.8 Semaphore 限流
    intent = rule_normalize(parse_json(raw))          # 规则校验/纠偏(§3.3)
    intent = validate(intent)                         # 字段/枚举/区间合法性
    if not intent["valid"]:
        intent["confidence"] = 0.0
        intent["clarify"] = intent["hint"]            # 非法→反问
    elif intent["confidence"] < CLARIFY_THRESHOLD:
        intent["clarify"] = clarify_question(intent)  # 例: "稳健按最大回撤<15% 还是波动率<10%?"
    intent["source"] = "llm"
    return intent

# 客户端: 收到 clarify → 展示问题 → 用户回答 → 再次调用 parse_nl(原query, ctx, history+QA)
# 服务端无状态, history 由客户端透传(或存 Redis screen:clarify:{session})
```

### 3.3 规则兜底引擎（低置信/失败）

```python
RULES = [
    (r"回撤[<\u2264]?\s*(\d+)%?", lambda m: [c("risk","<=",float(m.group(1)))]),
    (r"年化[>\u2265]?\s*(\d+)%?", lambda m: [c("ret",">=",float(m.group(1)))]),
    (r"夏普[>\u2265]?\s*([\d.]+)", lambda m: [c("sharpe",">=",float(m.group(1)))]),
    (r"稳健|低风险",          lambda m: [c("risk","<=",15), c("type","in",["bond","mixed"])]),  # 排除 index/etf(指数波动不低); mixed 待 equity_ratio 字段细化
    (r"主题[=:：]?\s*(\S+)",   lambda m: [c("theme","=",m.group(1))]),
    (r"近(.+?)收益靠前|排行",  lambda m: [c("window","=",map_window(m.group(1))), c("sort","composite","desc")]),
]

def rule_fallback(query) -> Optional[Intent]:
    conds = []
    for pat, fn in RULES:
        m = re.search(pat, query)
        if m: conds += fn(m)
    if not conds: return None
    return {"intent":"screen","conditions":conds,"sort":{"field":"composite","order":"desc"},
            "confidence":0.7,"clarify":None,"source":"rule"}

# 决策: LLM confidence<CLARIFY_THRESHOLD 或解析失败 → 试 rule_fallback；仍空 → 引导文案
```

### 3.4 SLA 评测内嵌（驱动兜底）

```python
def evaluate_nl(dataset: str) -> dict:
    """回归: 对 nl_eval_set(100)/nl_eval_set_adv(60) 逐条 parse_nl，与 gold 比 conditions。"""
    gold = load_gold(dataset)
    preds = [parse_nl(q, ctx_default) for q, _ in gold]
    acc = strict_acc(preds, gold)          # 字段/op/值全匹配
    return {"dataset": dataset, "acc": acc, "n": len(gold)}

# 门禁: 若 evaluate_nl("nl_eval_set")<0.85 → 生产默认走 rule_fallback 优先 + LLM 增强仅作候选，
#       并告警人工复核(DC-004)。评测可 CI 周期跑，不阻塞在线(§6)。
```

---

## 4. 数据结构

- 请求：`POST /api/screen/nl` `{"query","context":{"account_id"},"history":[QA]}`（history 可选）。
- 响应（对齐 §2.21，补全 `source`/`neg`）：
```json
{"intent":"screen",
 "conditions":[{"field":"type","op":"=","value":"mixed"},
               {"field":"risk","op":"<=","value":15},
               {"field":"window","op":"=","value":"1y"}],
 "sort":{"field":"composite","order":"desc"},
 "confidence":0.92,"clarify":null,"source":"llm"}
```
- `nl_mapping_log`（§3.4.4，可选）：`(query, intent_json, source, confidence, hit)` 用于评测迭代。

---

## 5. 边界与异常

| 场景 | 处理 |
|------|------|
| 歧义（稳健/低风险定义不清） | 返回 `clarify`，不臆测 |
| LLM 超时/429 | 捕获 → 转 `rule_fallback` → 仍空则引导文案（"试试：回撤<15% 且 年化>10%"） |
| 条件矛盾（回撤<5% 且 年化>30%） | 放行但结果可能为空，提示"条件过严，建议放宽"（§3.4 异常边界） |
| 空结果 | 返回空 + 建议放宽条件 |
| 主题词无映射 | `theme` 标 `unmapped`，降级为排除/忽略并提示 |

---

## 6. 并发与性能边界（§3.4.8）

- LLM 调用经 `asyncio.Semaphore(LLM_SEMAPHORE=5)`；超量入 `asyncio.Queue` 排队防 429。
- `rule_fallback` 同步、零 I/O，可作快速路径。
- `screen:{hash}` 缓存高频查询结果 TTL 5min（§2.8）。
- 评测（`evaluate_nl`）为离线 CI 任务，不占用在线配额。

---

## 7. 测试验收（test oracle）

| 验收项 | 基准 | 来源 |
|--------|------|------|
| 结构化集准确率 | strict acc = 1.0（规则层已证实） | 06_NL选基基线报告 |
| 混合分布 SLA | acc ≥ 0.85（LLM+规则+澄清） | DC-004 / §3.4.7 |
| 歧义不臆测 | confidence<阈值必带 clarify 或转兜底 | §3.4.7 |
| 来源可追溯 | 每条 intent 带 `source` | DC-004 |
| 限流有效 | 并发>5 不触 429（排队生效） | §3.4.8 |

---

## 8. 端到端执行流程

```
用户输入 → parse_nl(query, ctx, history)
  ├─ LLM(限流) → rule_normalize → validate
  │    ├─ conf≥0.85 → 返回 intent(source=llm)
  │    ├─ 0.60≤conf<0.85 → 返回 clarify(多轮)
  │    └─ conf<0.60 / 失败 → rule_fallback
  └─ rule_fallback 命中 → intent(source=rule)
       未命中 → 引导文案
intent.conditions → POST /api/screen(表单路径) 复用同一过滤引擎
```

---

## 9. 对现有文档的修订建议

1. **§2.21** `/api/screen/nl` 补 `source`/`neg`/`history` 字段与澄清响应结构。
2. **§3.4.2** 流程图补「规则兜底」分支与「history 透传」说明。
3. **新增** §3.4.9「NL 条件词表与澄清状态机（闭环 TP-02）」固化本方案。
4. 与 `07_LLM提示词设计稿` 对齐：prompt 必须输出本方案 `Intent` JSON 契约。

---

## 10. 专家评审修订闭环（E6）

| 编号 | 严重度 | 原问题 | 本版修订 | 状态 |
|------|--------|--------|----------|------|
| E6 | 🟠 高 | NL 规则兜底"低风险含 index/etf"（指数年波动~20%、回撤可达 30–40%，不属低风险） | 规则"稳健\|低风险"映射改 `type ∈ [bond, mixed]`（排除 index/etf）；`mixed` 待 `equity_ratio<0.3` 字段细化，避免权益仓位过高的偏股混合被误判低风险 | ✅ 已闭合 |

> 修订后 TP-02 由"修正后可编码"确认**可编码**。
