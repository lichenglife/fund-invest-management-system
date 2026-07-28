"""仪表盘(原型①；FR-D1~D6 / DC-001)。状态 -> 榜单 -> 学习 三段式首页。"""

import streamlit as st

st.title("📊 仪表盘")
st.caption("状态区(4卡) -> 榜单区(类型Tab + Top10) -> 学习区(学一基卡)")

with st.container(border=True):
    st.warning("🏗️ 建设中 · 关联 FR-D1~D6 / DC-001")
    st.caption("P1-12 仪表盘聚合接口 + P1-19a/b 状态区与榜单页待实现。")

pc = st.columns(4)
for col, label in zip(pc, ["组合收益", "基准收益", "待办", "学习进度"], strict=False):
    col.metric(label, "—")
