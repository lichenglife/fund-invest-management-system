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

ui.inject_global_style()
ui.page_header(
    "🧪 单基深度实验室",
    "把评估变推演 · 回本测算 / 情景推演 / 策略对照 + 联动模拟与笔记（FR-40~42）",
)

if api_client.is_mock():
    ui.mock_hint()

# 基金代码(实验室基于真实净值推演，§3.8.6 OQ-25)
fund_code = st.text_input("基金代码", value="000001.OF", help="输入基金代码(带后缀，如 000001.OF)")

# --- 回本测算器(FR-40 · BR-10.1) ---
bb_c, sc_c = st.columns(2)
with bb_c:
    with ui.panel("回本测算器", tag="FR-40 · BR-10.1"):
        # st.slider 不支持 format_func；用 format 参数格式化百分比
        loss_pct = st.slider(
            "当前收益率（亏损填负）",
            -0.60,
            0.0,
            -0.30,
            0.01,
            format="%+.0f%%",
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
        scs = api_client.get_lab_scenarios(fund_code)
        sdf = pd.DataFrame(
            [
                {
                    "情景": s["scenario"],
                    "预期年化": utils.pct_text(s.get("expected")),
                    "终值": round(s["final_value"], 4) if s.get("final_value") else None,
                    "对持仓影响": s.get("impact", ""),
                }
                for s in scs
            ]
        )
        st.dataframe(sdf, use_container_width=True, hide_index=True)

st.divider()

# --- 策略对照实验室(FR-42 · BR-10.3，五策略卡含回本联动) ---
with ui.panel("策略对照实验室", tag="FR-42 · BR-10.3 · 五策略 + 回本联动"):
    sts = api_client.get_lab_strategies(fund_code)
    stgdf = pd.DataFrame(sts).rename(
        columns={
            "name": "策略",
            "total_return": "总收益",
            "max_drawdown": "最大回撤",
            "note": "说明",
        }
    )
    st.dataframe(stgdf, use_container_width=True, hide_index=True)
    st.caption("测算结果可存笔记；亏损回本提示联动模拟交易持仓(BR-10.5)")

ui.source_footer()
