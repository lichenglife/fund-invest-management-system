"""持仓穿透与舆情(原型⑨；FR-43,44 / DC-012)。重仓股+来源时间/四维财务卡/舆情周评。"""

import streamlit as st

st.title("🔎 持仓穿透舆情")
st.caption("前十大(来源+时间，按占净值比排序) · 四维度财务卡 · 舆情周评(AI 统一出口)")

with st.container(border=True):
    st.warning("🏗️ 建设中 · 关联 FR-43,44 / DC-012")
    st.caption("P3-01a/b 穿透数据与舆情并发抓取 + P3-02a/b 页面待实现(Phase 3)。")
