"""基金评估详情(原型③；FR-06~09 / DC-003)。指标/五因子评分/风格箱/Brinson/研究卡。"""

import streamlit as st

st.title("🔬 基金评估详情")
st.caption("指标卡(区间/基准) · 五因子可解释评分 · 风格箱 · Brinson 归因 · 研究指标卡")

with st.container(border=True):
    st.warning("🏗️ 建设中 · 关联 FR-06~09 / DC-003")
    st.caption(
        "P1-03a~d 评估算法(ret/risk/perf/scale/manager) + P1-04a/b 接口 + P1-14a/b 页面待实现。"
        " 引擎唯一权威源(ADR-002)。"
    )
