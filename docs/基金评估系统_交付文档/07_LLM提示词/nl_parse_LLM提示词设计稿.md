# `nl_parse()` LLM 提示词设计稿

> 对应：DC-004 / 技术规格 `nl_parse(question) -> Union[StructuredCondition, Clarify]` / `NL_ACCURACY_TARGET=0.85`
> 前置：结构化基线 100%（`nl_eval_set.json`）+ 对抗样本 60%（`nl_eval_set_adv.json`），详见 `nl选基对抗样本评测报告.md`。
> 目的：把规则兜底基线在自由表述上 28% 的地板，拉升到混合分布 ≥85%，落实 DC-004「LLM 解析 + 规则兜底 + 歧义反问」。

---

## 1. 目标与定位

`nl_parse()` 的 LLM 层**只做一件事**：把用户任意自然语言（含错别字、中英混用、汉字数字、俚语、跨句指代）**映射为结构化筛选条件 JSON**。它不做基金推荐、不输出任何基金代码、不给出买卖建议——那是筛选器/评估引擎的职责。

```
用户问句 ──▶ [LLM 语义解析] ──▶ 结构化 JSON
                │                      │
                │                [规则层校验/归一]  (枚举/范围/兜底)
                │                      │
                └── 低置信/无效 ──▶ [规则兜底解析] ──▶ 结构化 JSON 或 Clarify
                                          │
                                    仍歧义 ──▶ Clarify(反问)
```

## 2. 设计原则

1. **映射不臆测**：问句没给的维度不填；数字必须来自问句或可归一的中文/汉字数字，不得编造。
2. **歧义必反问**：信息不足（无类型/区间/具体阈值）时返回 `clarify=true` + 反问句，绝不强填。
3. **只输出 JSON**：用 JSON Mode / function-calling 强制结构化，避免自由文本。
4. **可审计**：输出附带字段来源说明（"本解析仅基于用户输入语义，不含任何投资结论"）。
5. **规则层兜底**：LLM 输出经规则层二次校验与归一；LLM 失败/超时/低置信时回退规则解析。
6. **成本可控**：默认低价模型（DeepSeek-chat / 通义千问），单轮数百 token，不做批量。

## 3. 输出契约（JSON Schema）

```json
{
  "clarify": false,
  "clarify_question": null,
  "type": ["mixed"],
  "window": "3y",
  "factors": {
    "max_drawdown_le": 0.15,
    "return_rank_ge": 0.20,
    "annual_return_ge": 0.08,
    "volatility_le": 0.10,
    "scale_min": 2.0,
    "scale_max": 50.0,
    "sharpe_ge": 1.0
  },
  "exclude": ["新能源", "半导体"]
}
```

**枚举约束（必须与规则层一致，否则规则层拒收）**

| 字段 | 取值 | 语义 |
|------|------|------|
| `type` | `stock` / `mixed` / `bond` / `index` / `etf` / `qdii` / `money`（可多值） | 基金类型 |
| `window` | `1y` / `3y` / `5y` / `ytd` / `since` / `null` | 业绩区间；`since`=成立以来/长期 |
| `max_drawdown_le` | 小数（0.15=最大回撤≤15%） | 回撤上限 |
| `return_rank_ge` | 小数（0.20=收益排名前20%） | 收益排名下限 |
| `annual_return_ge` | 小数 | 年化收益下限 |
| `volatility_le` | 小数 | 年化波动率上限 |
| `scale_min` / `scale_max` | 亿元 | 规模区间 |
| `sharpe_ge` | 小数 | 夏普下限 |
| `exclude` | 行业/主题字符串数组 | 剔除项（须为已知行业词） |

> 注：`factors` 仅可含上表 7 个键；未知键（如 `beta`、`dividend`）一律忽略（对抗样本 §N 已验证）。

## 4. System Prompt（可复制）

```
你是一个基金筛选系统的「语义解析器」，负责把用户的自然语言需求转换为结构化筛选条件 JSON。
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
1. 中文/汉字数字 → 阿拉伯数字：十几个点→0.15；百分之二十→0.20；两成→0.20；五个点→0.05；两三个亿→scale_min=2,scale_max=3。
2. 错别字/谐音归一：混和→混合；收溢→收益；白九→白酒；股票鸡→股票基；波懂→波动；规莫→规模；忆→亿；考前→靠前；一念→一年；san年→三年；huode→获得。
3. 中英混用：low risk→低波动低回撤(max_drawdown_le≈0.15)；sharpe 高→sharpe_ge=1.0；volatile→volatility_le=0.10；high return/top 20%→return_rank_ge=0.20；long term→window=since。
4. 俚语映射：别坐过山车/躺赢/别一把亏光/稳稳/血本无归→低波动低回撤(volatility_le≈0.10 或 max_drawdown_le≈0.15)；跑赢余额宝两三倍→annual_return_ge≈0.06（标注为估算）。
5. 否定词（不要/别碰/剔除/避开/不买）+ 行业 → 放入 exclude。
6. 跨句指代（"跟上面那个差不多""就要昨天聊那种"）无法从本句解析 → clarify=true，反问请用户补充类型/区间/阈值。

# 反问原则
- 当 type 为空 且 window 为 null 且 无具体数字阈值 时，必须 clarify=true。
- 反问要具体、可选项化（如"您偏向哪类基金？看多长区间？"），不要泛泛而问。

# 禁止
- 禁止编造基金代码、名称、收益数字。
- 禁止输出 JSON 以外的文字。
- 禁止对缺失维度填默认值（如"规模适中"才可填 scale 2-50，纯"好基金"不可填）。
```

## 5. Few-shot 示例（覆盖 5 类失败模式 + 反问 + 跨句指代）

> 以 messages 形式注入；示例即对抗样本中的典型难例，使模型对齐期望映射。

**示例 1 — 标准结构化（对照基线 100%）**
- 用户：`近三年混合基金里回撤小于15%、收益排名前20%的`
- 输出：`{"clarify":false,"clarify_question":null,"type":["mixed"],"window":"3y","factors":{"max_drawdown_le":0.15,"return_rank_ge":0.20},"exclude":[]}`

**示例 2 — 错别字/谐音（对抗 M）**
- 用户：`近san年huode高、回撤小的混和基`
- 输出：`{"clarify":false,"clarify_question":null,"type":["mixed"],"window":"3y","factors":{"return_rank_ge":0.20,"max_drawdown_le":0.15},"exclude":[]}`
- 用户：`想买点主动混和，别碰白九`
- 输出：`{"clarify":false,"clarify_question":null,"type":["mixed"],"window":null,"factors":{},"exclude":["白酒"]}`

**示例 3 — 中英混用（对抗 N）**
- 用户：`sharpe 高一点，回撤小的股票`
- 输出：`{"clarify":false,"clarify_question":null,"type":["stock"],"window":null,"factors":{"sharpe_ge":1.0,"max_drawdown_le":0.15},"exclude":[]}`
- 用户：`ETF 别太 volatile，规模大些`
- 输出：`{"clarify":false,"clarify_question":null,"type":["etf"],"window":null,"factors":{"volatility_le":0.10,"scale_min":50.0},"exclude":[]}`

**示例 4 — 汉字/中文数字（对抗 O）**
- 用户：`回撤十几个点以内的混合`
- 输出：`{"clarify":false,"clarify_question":null,"type":["mixed"],"window":null,"factors":{"max_drawdown_le":0.15},"exclude":[]}`
- 用户：`收益前百分之二十的混合`
- 输出：`{"clarify":false,"clarify_question":null,"type":["mixed"],"window":null,"factors":{"return_rank_ge":0.20},"exclude":[]}`
- 用户：`规模两三个亿到五十亿的混合`
- 输出：`{"clarify":false,"clarify_question":null,"type":["mixed"],"window":null,"factors":{"scale_min":2.0,"scale_max":50.0},"exclude":[]}`

**示例 5 — 俚语（对抗 K）**
- 用户：`别坐过山车，稳稳的债基`
- 输出：`{"clarify":false,"clarify_question":null,"type":["bond"],"window":null,"factors":{"volatility_le":0.10},"exclude":[]}`
- 用户：`近一年别太刺激、能跑赢余额宝两三倍、别买新能源的混合`
- 输出：`{"clarify":false,"clarify_question":null,"type":["mixed"],"window":"1y","factors":{"annual_return_ge":0.06},"exclude":["新能源"]}`

**示例 6 — 歧义反问（对抗 E / L）**
- 用户：`想找个好一点的基金`
- 输出：`{"clarify":true,"clarify_question":"您偏向哪类基金（混合/股票/债券/指数等）？想看多长区间（近一年/三年/成立以来）的表现？","type":[],"window":null,"factors":{},"exclude":[]}`
- 用户：`跟上面那个差不多，但别碰白酒`
- 输出：`{"clarify":true,"clarify_question":"本轮为单句解析，无法获知『上面那个』的具体类型与区间，请补充：类型？区间？以及回撤/收益等阈值？","type":[],"window":null,"factors":{},"exclude":["白酒"]}`

**示例 7 — 组合自由表述（对抗 P）**
- 用户：`近三年涨得多跌得少、别买军工和半导体的股混`
- 输出：`{"clarify":false,"clarify_question":null,"type":["mixed"],"window":"3y","factors":{"return_rank_ge":0.20,"max_drawdown_le":0.15},"exclude":["军工","半导体"]}`

## 6. 与规则层 / 澄清的协同管线

```python
def nl_parse(question: str) -> Union[StructuredCondition, Clarify]:
    # 1) 规则层先快速判反问/简单结构化（便宜、零延迟）
    rule = rule_parse(question)
    if rule and rule.confidence_high:
        return rule                       # 规则能搞定就不调 LLM（省成本）
    # 2) 调 LLM
    try:
        raw = llm_chat(system=PROMPT, fewshot=EXAMPLES, user=question,
                       json_mode=True, timeout=3.0)
        obj = json.loads(raw)
    except (Timeout, JSONError):
        if rule: return rule              # LLM 失败→规则兜底
        return Clarify("没能理解您的需求，请补充基金类型与查看区间")
    # 3) 规则层校验/归一 LLM 输出（枚举/范围/未知键剔除）
    obj = rule_normalize(obj)
    if obj_invalid(obj):
        if rule: return rule
        return Clarify("需求不够明确，请补充类型/区间/阈值")
    if obj["clarify"]:
        return Clarify(obj["clarify_question"])
    return StructuredCondition(**obj)
```

关键点：
- **规则层是首道防线也是最后兜底**：简单句零延迟零成本；LLM 异常时保证主流程不阻塞。
- **LLM 输出必经 `rule_normalize`**：强制枚举、丢弃未知键、纠正越界值，防止模型漂移。
- **澄清只产生一次**：LLM 或规则任一层判定歧义即返回 `Clarify`，前端展示反问气泡。

## 7. 护栏与合规

- **不荐基**：输出纯结构化条件，绝不含基金代码/名称/买卖建议；前端在结果区固定标注"本解析仅基于您输入的自然语言语义，不构成投资建议"。
- **不臆测**：缺失维度留空；"跑赢余额宝两三倍"等需估算的数字，填近似值并在会话层注明"估算"。
- **溯源**：解析结果本身不产生数据，仅映射意图，故标注 `source="nl_parse(llm)"`、`as_of=null`；最终筛选数据由筛选器标注真实数据源（FR-46）。
- **防注入**：用户问句视为不可信输入；prompt 中固化"禁止输出 JSON 以外文字/禁止编造代码"，并对输出做 schema 校验。
- **降级**：LLM 超时/限频 → 规则兜底；规则也无解 → 引导式表单（DC-004 已定义），不阻塞。

## 8. 5 类失败模式的 prompt 对策映射

| 对抗失败模式 | 规则层准确 | prompt 对策 | 预期提升 |
|-------------|-----------|------------|---------|
| M 错别字/谐音 | 0% | §4 归一规则 2 + 示例 2 | 高 |
| N 中英混用 | 12% | §4 归一规则 3 + 示例 3 | 高 |
| O 汉字/中文数字 | 14% | §4 归一规则 1 + 示例 4 | 高 |
| K 俚语 | 33% | §4 归一规则 4 + 示例 5 | 中高 |
| L 跨句指代 | 70% | §4 归一规则 6 + 示例 6（clarify） | 结构保持，指代需会话状态 |

> 跨句指代（L）单句 LLM 无法解决，须依赖**会话上下文**（多轮维护最近一次结构化条件），属后续增强，不在首版 SLA 范围内。

## 9. 模型选型与成本

| 项 | 选型 | 说明 |
|----|------|------|
| 默认模型 | DeepSeek-chat / 通义千问-turbo | 低价、中文强、支持 JSON Mode |
| 上下文 | System(~600 tok) + 7 few-shot(~1.2k tok) + 用户(<50 tok) | 每轮 ≈ 2k token |
| 成本 | < 0.01 元/次 | 远低于人工，可常开 |
| 超时 | 3s | 超时即规则兜底 |
| 降级 | 规则层 + 引导表单 | 不影响主流程 |

## 10. 评测方案（160 条回归）

开发期 LLM 路径落地后，用现有语料做回归：

```bash
# 对 nl_eval_set.json(100) + nl_eval_set_adv.json(60) 各跑一遍 LLM 解析
# 复用 nl_baseline.py 的 evaluate() 比对 gold standard
python3.11 nl_baseline.py nl_eval_set.json      "LLM(结构化)"
python3.11 nl_baseline.py nl_eval_set_adv.json   "LLM(对抗)"
```

- **合格线**：合并 160 条**严格准确率 ≥ 85%**（`NL_ACCURACY_TARGET`）。
- **分维度**：`clarify` 类（E/L 中歧义句）必须返回 `clarify=true`；结构化类类型/区间/剔除严格匹配，因子阈值容差（ratio 0.02 / scale 1 亿）内计为通过。
- **回归门禁**：每次改 prompt/换模型须重跑 160 条；任一维度较上次下降 >2pp 阻塞合并。
- **持续扩充**：线上真实失败问句回流，补充进 `nl_eval_set_adv.json`，使评测集逼近真实分布。

## 11. 待确认 / 开放问题

1. **LLM API 密钥**：本设计稿未执行（沙箱无密钥）；落地需接入 DeepSeek/通义。
2. **跨句指代**：首版仅支持单句澄清，多轮会话上下文解析列为 v1.1 增强。
3. **估算数字口径**：如"跑赢余额宝两三倍"映射为 `annual_return_ge≈0.06` 是否可接受，需产品确认阈值。
4. **few-shot 数量**：7 例为起点，若某类仍弱可增例；注意 few-shot token 成本。
