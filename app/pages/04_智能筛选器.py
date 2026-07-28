"""智能筛选器(原型④；FR-11~14 / DC-004)。条件表单 + NL解析 + 排序 + 相似去重。"""

import streamlit as st

st.title("🔍 智能筛选器")
st.caption("左表单(AND/OR) + 右实时结果 · NL 解析回显 · 单因子排序 · 相似去重(≥70%)")

with st.container(border=True):
    st.warning("🏗️ 建设中 · 关联 FR-11~14 / DC-004")
    st.caption(
        "P1-06a 表单过滤 + P1-06b NL解析(LLM+规则+澄清) + P1-06c 去重 + P1-15a/b 页面待实现。"
    )

st.text_input("自然语言筛选", placeholder="如 近一年收益靠前的稳健混合基")
