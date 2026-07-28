"""infra.external · 外部数据源/LLM 适配器(§2.15 容错 / TP-02 / TP-06)。

占位：P1-01a AkShare 适配器、P1-01b Tushare fallback、P1-06b LLM 客户端将在此落地。
约定(§2.15 / §8.5)：任意外部调用须有超时 + fallback；AkShare 失 -> Tushare，
LLM 失 -> 规则摘要(50303)；降级须可观测(degraded=true)。
"""

__all__: list[str] = []

# TODO(P1-01a, FR-36/46): AkShareDataSource
# TODO(P1-01b, FR-36): TushareDataSource (fallback)
# TODO(P1-06b, FR-12/13): LLMClient (LangChain + cheap LLM, R7 待 key)
