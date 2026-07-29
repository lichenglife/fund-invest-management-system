"""组合与配置(原型⑥；FR-20~24,37 / DC-006；P1-08a~d + P1-17a/b)。

核心-卫星构建(从模拟导入) · 多层级诊断(红黄绿) · 回测(vs沪深300) · 再平衡(偏离±5%)。
验证点：诊断是否 actionable。股债目标仓位由 risk_type 推导(E8/E9/E12)。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from app import api_client, state, utils  # noqa: E402
from app.components import diagnosis_table, ui  # noqa: E402
from app.mock import store  # noqa: E402

st.title("🧩 组合与配置")
st.caption("核心-卫星 · 多层级诊断(红黄绿) · 回测 · 再平衡提醒(偏离 ±5%)")

if api_client.is_mock():
    ui.mock_hint()

# --- 组合构建(核心-卫星 · BR-5.1) ---
build_c, diag_c = st.columns([1, 2])
with build_c:
    with ui.panel("组合构建", tag="BR-5.1 · 核心-卫星"):
        comps = state.portfolio_components()
        edf = pd.DataFrame(
            [
                {
                    "名称": c["name"],
                    "角色": c["role"],
                    "权重": f"{c['weight']*100:.0f}%",
                }
                for c in comps
            ]
        )
        st.dataframe(edf, use_container_width=True, hide_index=True)
        total_w = sum(c["weight"] for c in comps)
        st.caption(f"权重合计：{total_w*100:.0f}%（目标=100%）")
        if st.button("👉 从模拟持仓一键导入", help="原型⑥ BR-5.1"):
            pos = state.paper_positions()
            if pos:
                st.session_state["portfolio_components"] = [
                    {"name": p["name"], "code": p["code"], "weight": 1.0 / len(pos), "role": "导入"}
                    for p in pos
                ]
                st.success(f"已导入 {len(pos)} 只持仓")
                st.rerun()
            else:
                st.info("模拟持仓为空，先去模拟交易买入")
        if st.button("▶ 运行诊断", type="primary"):
            st.session_state["_run_diag"] = True
        st.caption("进入组合即自动跑多层级诊断(BR-5.12)")

with diag_c:
    if st.session_state.get("_run_diag") or True:  # 原型：进入即自动诊断
        diagnosis_table.render(api_client.get_portfolio_diagnosis(), store.PORTFOLIO_RISK_TYPE)

st.divider()

# --- 历史回测(BR-5.2) + 再平衡(BR-5.5) ---
bt_c, reb_c = st.columns(2)
with bt_c:
    with ui.panel("历史回测", tag="BR-5.2 · vs 沪深300 · 默认近3年"):
        st.caption("回测曲线：组合 vs 沪深300 · 收益/回撤/夏普（统一后复权净值 E3/E14）")
        # 用 110011 净值序列示意组合曲线
        navs = store.nav_series("110011", days=180)
        cdf = (
            pd.DataFrame(navs)
            .set_index("trade_date")[["adj_nav"]]
            .rename(columns={"adj_nav": "组合"})
        )
        st.line_chart(cdf, use_container_width=True)
        st.caption("区间可改 · 严格时序(禁未来函数)")
with reb_c:
    with ui.panel("再平衡提醒", tag="BR-5.5 · 偏离 ±5%"):
        st.write("股债偏离阈值提醒，可设频率；给出再平衡建议")
        drift = st.slider("当前股债偏离 (%)", 0, 20, 6)
        if drift > 5:
            st.warning(f"⚠ 偏离 {drift}% 超过 ±5% 阈值，建议再平衡")
        else:
            st.success(f"偏离 {drift}% 在阈值内，维持")
        st.caption("相关性矩阵：成分基金两两相关(待后端计算)")

ui.source_footer()
