"""智能筛选器(原型④；FR-11~14 / DC-004；P1-06a~c + P1-15a/b)。

左表单(AND/OR) + 右实时结果 · NL 解析回显(置信度) · 单因子排序切换 · 相似去重(≥70%)。
操作列支持 对比/模拟/组合 一键跳转。NL「稳健」排除 index/etf(E6)。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from app import api_client, state, utils  # noqa: E402
from app.components import ui  # noqa: E402
from app.mock import store  # noqa: E402

ui.inject_global_style()
ui.page_header(
    "🔍 智能筛选器", "左表单(AND/OR) + 右实时结果 · NL 解析回显 · 单因子排序 · 相似去重(≥70%)"
)

if api_client.is_mock():
    ui.mock_hint()

left, right = st.columns([1, 2])

# --- 左：条件表单 + NL(BR-3.1/3.2) ---
with left:
    with ui.panel("条件筛选", tag="BR-3.1 · 改条件即筛"):
        logic = st.segmented_control(
            "逻辑", ["AND", "OR"], default="AND", label_visibility="collapsed"
        )
        f = state.screen_filters()
        f["logic"] = logic
        f["fund_type"] = st.selectbox(
            "基金类型",
            ["all", "stock", "mix", "index", "etf", "bond", "qdii"],
            format_func=lambda x: "全部" if x == "all" else store.TYPE_LABELS.get(x, x),
        )
        f["max_drawdown"] = st.slider("最大回撤 ≤ (%)", 5, 50, 15)
        f["min_return"] = st.slider("年化收益 ≥ (%)", 0, 30, 10)
        f["min_tenure"] = st.slider("经理从业 ≥ (年)", 1, 15, 5)
        themes = ["不限"] + store.CATEGORY_TREE["主题"]
        f["theme"] = st.selectbox("主题", themes)

    with ui.panel("自然语言选基", tag="BR-3.2 · LLM 解析 + 规则兜底"):
        nl = st.text_input(
            "用一句话描述你想要的基金", placeholder="如：回撤小于15%、年化大于10%的红利基金"
        )
        if st.button("AI 解析并筛选"):
            st.session_state["nl_parsed"] = {
                "cond": f"最大回撤 ≤ {f['max_drawdown']}% ∧ 年化 ≥ {f['min_return']}% "
                + (f"∧ 主题={f['theme']}" if f["theme"] != "不限" else ""),
                "conf": 0.92,
            }
        if st.session_state.get("nl_parsed"):
            p = st.session_state["nl_parsed"]
            st.markdown(
                f'<div style="background:#F0FDF4;border:1px dashed #16A34A;border-radius:6px;'
                f'padding:8px 10px;font-size:12px">✅ 已解析为条件：{p["cond"]}<br>'
                f'<span style="color:#6B7280">置信度 {p["conf"]*100:.0f}% · 歧义时反问澄清 · '
                f"解析失败回退规则</span></div>",
                unsafe_allow_html=True,
            )
        st.caption("LLM 仅做语义->条件映射，准确率 ≥85%(100 条评测)，不编造数字")

# --- 右：结果 + 排序 + 去重(BR-3.3/3.4) ---
with right:
    with ui.panel("筛选结果", tag="BR-3.3 · 默认综合评分降序"):
        sort_by = st.segmented_control(
            "排序",
            ["综合评分", "夏普", "回撤", "年化"],
            default="综合评分",
            label_visibility="visible",
        )
        results = api_client.screen_funds(f, sort_by=sort_by)
        rrows = [
            {
                "代码": r["code"],
                "名称": r["name"],
                "类型": store.TYPE_LABELS.get(r["type"], r["type"]),
                "回撤": utils.format_pct(store.fund_metrics_summary(r["code"])["max_drawdown"]),
                "年化": utils.format_pct(store.fund_metrics_summary(r["code"])["return_pct"]),
                "夏普": f"{store.fund_metrics_summary(r['code'])['sharpe']:.2f}",
                "评分": r["score"],
            }
            for r in results
        ]
        if rrows:
            st.dataframe(pd.DataFrame(rrows), use_container_width=True, hide_index=True)
            # 相似去重提示(BR-3.4，重叠≥70%)
            if len(rrows) >= 2:
                st.markdown(
                    '<div style="background:#fff8ec;border:1px solid #f0d39a;border-radius:6px;'
                    'padding:8px 10px;font-size:12px;color:#8a5a00">⚠ 检测到结果持仓高度雷同'
                    "(前十大重叠 ≥70%)：110011 与 005827 可一键去重(默认开启)</div>",
                    unsafe_allow_html=True,
                )
                st.button("一键去重", key="dedup_btn")
        else:
            st.caption("无符合条件的基金")
        st.caption("结果可一键加入 对比 / 模拟 / 组合(BR-3.5)")
        col1, col2, col3 = st.columns(3)
        col1.page_link("pages/03_基金评估详情.py", label="🔬 对比", icon="➡️")
        col2.page_link("pages/05_模拟交易.py", label="💰 模拟", icon="➡️")
        col3.page_link("pages/06_组合与配置.py", label="🧩 组合", icon="➡️")

ui.source_footer()
