"""仪表盘(原型①；FR-D1~D6 / DC-001；P1-12/P1-19a/b)。

三段式首页：状态(4卡) -> 榜单(类型Tab + Top10 综合评分) -> 学习区(学一基卡)。
验证点：进首页即得学习线索。评分口径见评估引擎(ADR-002 唯一权威源)。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from app import api_client, state, utils  # noqa: E402
from app.components.ui import fold, metric_row, mock_hint, source_footer  # noqa: E402

st.title("📊 仪表盘")
st.caption("状态 -> 榜单 -> 学习 三段式（FR-D1~D6）· 验证点：进首页即得学习线索")

if api_client.is_mock():
    mock_hint()

# --- 状态区(FR-D1/D5 顶部 4 卡) ---
data = api_client.get_dashboard()
metric_row(data["status"])

st.divider()

# --- 榜单区：类型 Tab + Top10(FR-D2/D5) ---
st.markdown("#### 🏆 综合评分榜")
tabs_cfg = [
    ("全部", "all"),
    ("股票型", "stock"),
    ("混合型", "mix"),
    ("指数/ETF", "etf"),
    ("债券型", "bond"),
    ("QDII", "qdii"),
    ("货币", "money"),
]
tab_labels = [t[0] for t in tabs_cfg]
tabs = st.tabs(tab_labels)

for tab, (_label, ftype) in zip(tabs, tabs_cfg, strict=False):
    with tab:
        rows = api_client.get_dashboard(ftype)["top10"]
        if rows:
            df = pd.DataFrame(rows)
            df = df.rename(columns={"score": "综合评分"})
            st.dataframe(df, use_container_width=True, hide_index=True)
            st.caption("评分=多因子综合(收益/风险/性价比/规模/经理)，可解释")
        else:
            st.caption("该类型暂无上榜基金")

# --- 近期动态(FR-D3) ---
st.markdown("#### 📰 近期动态")
for line in data["dynamics"]:
    st.markdown(f"- {line}")

st.divider()

# --- 学习区(FR-D4/D5 底部：学一基卡 + 学习入口) ---
lc, le = st.columns([3, 2])
with lc:
    with st.container(border=True):
        st.markdown("##### 📘 学一基 · 今日（FR-D4）")
        st.markdown(f"**「{data['learn_card']['title']}」**")
        st.write(data["learn_card"]["desc"])
        c1, c2 = st.columns(2)
        c1.page_link("pages/02_基金数据中心.py", label="🗂️ 看档案", icon="➡️")
        c2.page_link("pages/10_学习投教.py", label="📚 指标词典", icon="➡️")
with le:
    with st.container(border=True):
        st.markdown("##### 学习入口")
        for icon, name, page in [
            ("📖", "指标词典", "pages/10_学习投教.py"),
            ("🗺️", "学习路径", "pages/10_学习投教.py"),
            ("📉", "案例回放", "pages/10_学习投教.py"),
            ("🧠", "行为金融", "pages/10_学习投教.py"),
        ]:
            st.page_link(page, label=f"{icon} {name}", icon="➡️")

# --- 折叠次要(FR-D6) ---
fold(
    "高级 / 低频功能（折叠 · FR-D6）",
    "原始数据导出 · 评分参数调优 · API 接入 · 数据源切换（AkShare/Tushare）",
)

source_footer(source="AkShare", extra="评分口径见评估引擎 ADR-002")
st.caption(utils.mock_badge() if api_client.is_mock() else "仅供参考，不构成投资建议（§5.2）")

# 角色与学习进度写回 state(原型§2 顶部栏联动)
state.ensure("role", "学习者")
