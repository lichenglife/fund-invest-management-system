"""学习投教(原型⑩；FR-25~28,47,48 / DC-007；P2-05a/b + P2-06a/b)。

指标词典(全站 tooltip) · 角色三阶段路径 · 案例回放沙盒(独立) · 行为金融问卷 · 笔记。
验证点：学习是否体系。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from app import api_client  # noqa: E402
from app.components import ui  # noqa: E402

st.title("📚 学习投教")
st.caption("指标词典(全站 tooltip) · 角色三阶段路径 · 案例回放沙盒 · 行为金融问卷 · 笔记")

if api_client.is_mock():
    ui.mock_hint()

learn = api_client.get_learn()

# --- 指标词典(BR-6.1) + 学习路径(BR-6.3) ---
glo_c, path_c = st.columns(2)
with glo_c:
    with ui.panel("指标词典", tag="BR-6.1 · 大白话+公式+好坏区间 · 全站 tooltip 可引用"):
        for g in learn["glossary"]:
            with st.expander(f"{g['term']}　（好坏：{g['good']}）"):
                st.write(f"**定义**：{g['def']}")
                st.write(f"**公式**：`{g['formula']}`")
                st.write(f"**好坏区间**：{g['range']}")
with path_c:
    with ui.panel("学习路径", tag="BR-6.3 · 角色三阶段 + 可跳转"):
        for p in learn["path"]:
            st.markdown(f"**{p['stage']}** -> {p['modules']}")
        st.page_link("pages/01_仪表盘.py", label="入门：仪表盘", icon="➡️")
        st.page_link("pages/03_基金评估详情.py", label="进阶：评估详情", icon="➡️")
        st.page_link("pages/05_模拟交易.py", label="实战：模拟交易", icon="➡️")

st.divider()

# --- 案例回放沙盒(FR-47/BR-6.5，独立沙盒) + 行为金融(FR-48/BR-6.6) ---
case_c, bias_c = st.columns(2)
with case_c:
    with ui.panel("案例回放", tag="FR-47/BR-6.5 · 独立沙盒，不影响主账户"):
        for c in learn["cases"]:
            st.button(c, key=f"case_{c}")
        st.caption("在模拟盘重演极端行情，你做买卖决策并被记录复盘；独立沙盒，不影响主账户")
with bias_c:
    with ui.panel("行为金融", tag="FR-48/BR-6.6 · 科普卡 + 自评问卷 + 改进建议"):
        st.write("认知偏差自评（勾选符合你的项）：")
        checked = []
        for q in learn["bias_questions"]:
            if st.checkbox(q, key=f"bias_{q}"):
                checked.append(q)
        if checked:
            st.info(f"检测到 {len(checked)} 项偏差倾向 -> 建议：纪律定投 / 预设止损，避免追涨杀跌")

# --- 个人研究笔记(FR-28/BR-6.4) ---
with ui.panel("个人研究笔记", tag="FR-28/BR-6.4 · 可记可搜，关联基金/指标"):
    note = st.text_area(
        "记一条笔记（如回本测算存笔记）", placeholder="例：110011 估值低位定投加仓…"
    )
    if st.button("保存笔记") and note:
        st.success("已保存（关联基金/指标，可搜索）")

ui.source_footer()
