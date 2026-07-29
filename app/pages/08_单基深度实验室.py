"""单基深度实验室(原型⑧；FR-40~42 / DC-011；P1-09a/b + P1-18a/b)。

把评估变推演：回本测算(存笔记/联动持仓) · 三情景推演(对持仓影响) · 五策略对照卡。
回本公式：回本需涨 = |亏损| / (1 + 亏损)(DC-011/BR-10.1；TP-04)。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from app import api_client, utils  # noqa: E402
from app.components import ui  # noqa: E402

st.title("🧪 单基深度实验室")
st.caption("把评估变推演 · 回本测算 / 情景推演 / 策略对照 + 联动模拟与笔记（FR-40~42）")

if api_client.is_mock():
    ui.mock_hint()

# --- 回本测算器(FR-40 · BR-10.1) ---
bb_c, sc_c = st.columns(2)
with bb_c:
    with ui.panel("回本测算器", tag="FR-40 · BR-10.1"):
        loss_pct = st.slider(
            "当前收益率（亏损填负）",
            -0.60,
            0.0,
            -0.30,
            0.01,
            format_func=lambda x: f"{x*100:+.0f}%",
        )
        need = utils.breakeven_need(loss_pct)
        st.metric("回本需涨", f"+{need*100:.1f}%")
        st.caption("保守情景回本：~3年 / 基准：~2年 / 乐观：~1年")
        st.caption("公式：回本需涨 = |亏损| / (1 + 亏损) · 输入须来自数据中心真实净值(BR-10.4)")
        if st.button("💾 存笔记 / 联动模拟持仓", help="BR-10.5"):
            st.success("已记录回本测算笔记，可联动模拟交易持仓")

# --- 情景推演(FR-41 · BR-10.2，含对持仓影响列) ---
with sc_c:
    with ui.panel("情景推演", tag="FR-41 · BR-10.2 · 含对持仓影响"):
        scs = api_client.get_lab_scenarios()
        sdf = pd.DataFrame(
            [
                {
                    "情景": s["scenario"],
                    "目标点位": s["target"],
                    "预期回报": utils.pct_text(s["expected"]),
                    "对持仓影响": s["impact"],
                }
                for s in scs
            ]
        )
        st.dataframe(sdf, use_container_width=True, hide_index=True)

st.divider()

# --- 策略对照实验室(FR-42 · BR-10.3，五策略卡含回本联动) ---
with ui.panel("策略对照实验室", tag="FR-42 · BR-10.3 · 五策略 + 回本联动"):
    sts = api_client.get_lab_strategies()
    stgdf = pd.DataFrame(sts).rename(
        columns={
            "strategy": "策略",
            "cond": "适用条件",
            "pro_con": "优劣",
            "fit": "适合人群",
        }
    )
    st.dataframe(stgdf, use_container_width=True, hide_index=True)
    st.caption("测算结果可存笔记；亏损回本提示联动模拟交易持仓(BR-10.5)")

ui.source_footer()
