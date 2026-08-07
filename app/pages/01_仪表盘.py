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
from app.components.ranking_table import ranking_table  # noqa: E402
from app.components.ui import (  # noqa: E402
    fold,
    inject_global_style,
    kpi_grid,
    metric_row,
    page_header,
    source_footer,
    warning_banner,
)
from app.mock import store  # noqa: E402

inject_global_style()
page_header("📊 仪表盘", "状态 -> 榜单 -> 学习 三段式（FR-D1~D6）· 进首页即得学习线索")

if api_client.is_mock():
    warning_banner("当前为示例数据 · 对应后端接口待实现（开发计划 P1/P2/P3）", key="mock", icon="🏗️")

# --- 状态区(FR-D1/D5) ---
# 1) 两张 KPI 卡：组合收益 vs 沪深300，正红/负绿(红涨绿跌)，响应式网格(auto-fit)回流
kpis = store.DASHBOARD_KPIS
kpi_cards = []
for k in kpis:
    rp = k["return_pct"]
    # delta 传超额收益文本(组合卡显示相对基准超额，基准卡无)
    delta_str = utils.pct_text(k["delta"]) if k.get("delta") is not None else None
    kpi_cards.append(
        {
            "label": k["label"],
            "value": utils.pct_text(rp),
            "period": k.get("period"),
            "delta": delta_str,
            "is_positive": rp >= 0,
        }
    )
kpi_grid(kpi_cards)
# 2) 次要状态卡(待办/学习进度)
data = api_client.get_dashboard()
metric_row(store.DASHBOARD_STATUS)

st.divider()

# --- 榜单区：类型 Tab + Top10(FR-D2/D5) ---
top_cols = st.columns([3, 2])
with top_cols[0]:
    st.markdown('<div class="fl-section-title">🏆 综合评分榜</div>', unsafe_allow_html=True)
with top_cols[1]:
    st.markdown(
        f'<div class="fl-table-toolbar">'
        f'<span class="fl-badge as-of">数据截至 {store.AS_OF.isoformat()}</span>'
        f'<span class="fl-badge mock">{utils.mock_badge()}</span>'
        f"</div>",
        unsafe_allow_html=True,
    )
tabs_cfg = [
    ("全部", "all"),
    ("股票型", "stock"),
    ("混合型", "mixed"),
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
            df = pd.DataFrame(rows).rename(columns={"score": "综合评分"})
            # 自定义列宽：rank 窄 / code 等宽(数字定长) / name 大 / type 中 / 评分 小
            # badge(数据截至/示例数据)已在标题行展示，Tab 内不重复传
            ranking_table(
                df,
                columns_config={
                    "rank": st.column_config.NumberColumn("排名", width="small"),
                    "code": st.column_config.TextColumn("代码", width="small"),
                    "name": st.column_config.TextColumn("名称", width="large"),
                    "type": st.column_config.TextColumn("类型", width="small"),
                    "综合评分": st.column_config.NumberColumn("综合评分", width="small"),
                },
                caption="评分=多因子综合(收益/风险/性价比/规模/经理)，可解释",
            )
        else:
            st.caption("该类型暂无上榜基金")

# --- 近期动态(FR-D3) ---
st.markdown("#### 📰 近期动态")
ui.dyn_list(data["dynamics"])

st.divider()

# --- 学习区(FR-D4/D5 底部：学一基渐变卡 + 学习入口) ---
lc, le = st.columns([3, 2])
with lc:
    ui.learn_card(f"「{data['learn_card']['title']}」", data["learn_card"]["desc"])
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
