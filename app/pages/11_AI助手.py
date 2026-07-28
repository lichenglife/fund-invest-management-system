"""AI 助手(原型⑪；FR-29~32 / DC-008)。RAG对话/周报/持仓舆情周评/拒答降级。"""

import streamlit as st

st.title("🤖 AI 助手")
st.caption("RAG 对话(来源+拒答) · 周报 · 持仓舆情周评 · 失败降级回退规则摘要")

with st.container(border=True):
    st.warning("🏗️ 建设中 · 关联 FR-29~32 / DC-008")
    st.caption(
        "P3-03a/b RAG 检索问答 + 周报 worker + P3-04a/b 页面待实现(Phase 3)。"
        " 依赖 LLM key(TP-06 R7，C1 待确认)。"
    )
