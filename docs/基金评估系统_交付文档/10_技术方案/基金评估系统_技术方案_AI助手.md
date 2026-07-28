# 技术方案 TP-06 · AI 智能助手（RAG 检索 + 周报 Worker）

> **对应模块**：§3.11 AI 智能助手（BRD 模块七 FR-29~32，DC-008）
> **目标**：将 AI 助手从「async + 周报 worker」描述落地为**可直接编码**的 RAG 建库/检索/重排、对话上下文与周报生成流程。
> **前置依赖**：详细设计 §3.11/§3.11.7、技术规格 ai/rag.py + ai/report.py、07_LLM提示词、08_背景资料

---

## 1. 范围与目标

- 对话：基于投教语料 + 用户组合数据的 RAG 问答（多轮上下文）。
- 周报：定时汇总市场/组合/持仓变动 → LLM 生成 → 落库 → 作为 AI 周评统一出口（§3.9.6）。

---

## 2. 现有设计缺口

| 缺口 | 本方案处置 |
|------|-----------|
| RAG 建库/检索/重排未定义 | §3.1 |
| 周报 worker 触发与落库未定义 | §3.2 |
| 对话上下文管理未定义 | §3.3 |

---

## 3.1 RAG 建库与检索

```python
# 建库(离线/启动时): 语料 = 08_背景资料 + 基金知识卡 + 用户组合快照
def build_index(corpus: list[Doc]):
    chroma.delete_collection("fund_rag")              # 幂等重建
    for doc in chunk(corpus, size=800, overlap=80):   # 切片
        chroma.add(embed(doc.text), metadata={**doc.meta})

def rag_answer(query, ctx, history) -> str:
    hits = chroma.query(embed(query), top_k=8)        # 向量检索
    hits = rerank(query, hits, top_k=4)               # 交叉编码器重排
    prompt = build_qa_prompt(query, hits, ctx, history)  # 注入检索上下文
    return llm_complete(prompt)                       # 受 LLM_SEMAPHORE 限流(§3.4.8)
```

> 数据安全：RAG 上下文仅含当前用户授权数据；投教语料公开，不过敏。

### 3.2 周报 Worker（§3.11.7，独立进程）

```python
def weekly_report_job():                              # §3.14 定时(如周六 08:00)
    for uid in all_users():
        ctx = {"market": macro_snapshot(),            # §3.7
               "portfolio": portfolio_summary(uid),   # §3.6
               "holdings_chg": holdings_delta(uid, days=7),
               "sentiment": latest_sentiment(uid)}    # §3.9
        report = llm_complete(build_report_prompt(ctx))
        save_weekly_report(uid, report)               # weekly_reports 表
        link_to_sentiment(uid, report)                # §3.9.6 统一出口
```

> 异步：`weekly_report_job` 为独立 worker（§2.22.3 单点/协调），避免阻塞 API；失败重试 + 告警。

### 3.3 对话上下文

- 会话：`ai:session:{session_id}` 存最近 N 轮（QA + 检索命中），TTL 1h。
- 多轮：客户端透传 `session_id`；服务端拼 `history` 进 prompt，保证指代消解。

---

## 4. 数据结构

- 请求：`POST /api/ai/chat` `{"query","session_id","context":{"account_id"}}`
- 响应：`{"answer","citations":[doc_id],"session_id"}`
- `weekly_reports(uid PK, report_text, week_start, created_at)`

---

## 5. 边界与异常

| 场景 | 处理 |
|------|------|
| RAG 无命中 | 标注"基于通用知识"，不编造具体基金数据 |
| LLM 超时/429 | 转规则引导 + 重试；超限返回降级文案 |
| 周报生成失败 | 重试 2 次；仍失败告警，不阻塞其他用户 |
| 敏感数据 | RAG 不索引持仓明细外的隐私字段 |

---

## 6. 并发与性能（§3.11.7）

- 对话：`async` + `LLM_SEMAPHORE`（§3.4.8）。
- 周报：`ProcessPoolExecutor` 按用户分片并行；Chroma 单一存储（ADR-003）。
- API 多副本；worker 单点协调（§3.14.6 锁）。

---

## 7. 测试验收

| 项 | 基准 |
|----|------|
| RAG 命中 | 投教类问题 top-1 命中 08_背景资料相关切片 |
| 周报产出 | 每周每用户 1 篇，含市场/组合/持仓三节 |
| 限流 | 并发对话不触 429 |
| 无幻觉 | 引用 `citations` 非空或可溯源 |

---

## 8. 执行流程

```
对话: POST /api/ai/chat → build_index(已建) → rag_answer(检索+重排+LLM) → 响应
周报: 定时 → weekly_report_job(每用户) → 落库 + 联动舆情周评
```

---

## 9. 修订建议

1. **§3.11** 补「3.11.x RAG 与周报流程（闭环 TP-06）」固化本方案。
2. 技术规格 `ai/rag.py`/`ai/report.py` 注释对齐 `top_k`/`rerank`/`weekly_report_job`。
