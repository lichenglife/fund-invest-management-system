"""模拟交易(原型⑤；FR-15~19 / DC-005)。T日净值成交/持仓看板/定投回测/回本联动。"""

import streamlit as st

st.title("💰 模拟交易")
st.caption("账户四卡 · T 日收盘净值成交(非交易时段顺延) · 持仓看板 · 历史定投回测 · 复盘笔记")

with st.container(border=True):
    st.warning("🏗️ 建设中 · 关联 FR-15~19 / DC-005")
    st.caption("P1-07a~e 账户/买卖/回测 + P1-16a/b 页面待实现。强调：不连通实盘。")

pc = st.columns(4)
for col, label in zip(pc, ["总资产", "持仓市值", "可用现金", "累计盈亏"], strict=False):
    col.metric(label, "—")
