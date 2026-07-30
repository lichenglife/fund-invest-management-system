"""风险与监控(原型⑫；FR-33~36 / DC-009；P2-03a~c + P2-04a/b)。

风险偏好测评(联动默认配置) · 预警中心(多类聚合) · 估值定投信号(PE分位->倍数)
· 数据质量看板(Must) · 高位信号排查(与宏观共享引擎 FR-38)。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from app import api_client, utils  # noqa: E402
from app.components import ui  # noqa: E402

ui.inject_global_style()
ui.page_header(
    "🛡️ 风险与监控", "风险测评 · 预警中心 · 估值定投信号(PE分位->倍数) · 数据质量 · 高位排查"
)

if api_client.is_mock():
    ui.mock_hint()

risk = api_client.get_risk()

# --- 风险测评(FR-33) + 预警中心(FR-34) ---
as_c, al_c = st.columns(2)
with as_c:
    with ui.panel("风险偏好测评", tag="FR-33 · 联动默认配置与模拟起点仓位"):
        st.write("问卷判定 **稳健 / 均衡 / 积极**")
        rt = st.radio("示例判定", risk["types"], label_visibility="collapsed")
        st.info(f"-> {rt}：联动默认配置建议 + 模拟交易起点仓位（股债目标仓位由 risk_type 推导 E8）")
        st.button("开始测评")
with al_c:
    with ui.panel("预警中心", tag="FR-34 · 多类聚合 + 可设提醒频率"):
        for a in risk["alerts"]:
            st.markdown(f"- **{a['type']}**：{a['text']}")
        st.caption("站内展示 + 可设提醒频率")

st.divider()

# --- 估值定投信号(FR-35，PE分位->倍数) + 数据质量(FR-36 Must) ---
va_c, dq_c = st.columns(2)
with va_c:
    with ui.panel("估值定投信号", tag="FR-35 · PE 分位 -> 定投倍数"):
        vdf = pd.DataFrame(
            [
                {
                    "沪深300 PE 分位": v["pe_range"],
                    "定投倍数": v["multiple"],
                    "动作": v["action"],
                }
                for v in risk["valuation_dca"]
            ]
        )
        st.dataframe(vdf, use_container_width=True, hide_index=True)
        st.caption("站内信号红点 + 可订阅 · 与仪表盘动态卡共用引擎")
with dq_c:
    with ui.panel("数据质量监控", tag="FR-36 · Must"):
        items = risk["data_quality"]
        cols = st.columns(len(items)) if items else st.columns(1)
        for col, it in zip(cols, items, strict=False):
            with col:
                color = utils.level_color(it["level"])
                st.metric(it["k"], it["v"])
                st.caption(it["d"])
        st.error("⚠ 数据错了比没有更糟：异常实时告警 + 质量看板")

st.divider()

# --- 高位信号排查(FR-38 · 与宏观共享引擎) ---
with ui.panel("高位信号排查", tag="FR-38 · 与宏观共享同一引擎"):
    for h in risk["high_signal"]:
        st.markdown(
            f"- **{h['dim']}** " + ui.status_pill(h["level"], h["signal"]), unsafe_allow_html=True
        )
    st.success(f"综合：{risk['high_verdict']}")
    st.caption("全局输出标注数据截至时间与免责声明(FR-46)")
