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

ui.inject_global_style()
ui.page_header("🧩 组合与配置", "核心-卫星 · 多层级诊断(红黄绿) · 回测 · 再平衡提醒(偏离 ±5%)")

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
    with ui.panel("历史回测", tag="BR-5.2 · vs 沪深300全收益 · 默认近3年"):
        bt = api_client.get_portfolio_backtest()
        if bt.get("available") is False:
            st.caption(bt.get("note", "回测数据不足(组合或净值缺失)"))
            navs = store.nav_series("110011", days=180)  # mock 示意
            cdf = pd.DataFrame(navs).set_index("trade_date")[["adj_nav"]].rename(
                columns={"adj_nav": "组合(示意)"}
            )
            st.line_chart(cdf, use_container_width=True)
        else:
            # 真实回测：画组合净值曲线 + 指标
            curve = bt.get("nav_curve", [])
            if curve:
                cdf = pd.DataFrame(curve).set_index("date")[["nav"]].rename(columns={"nav": "组合"})
                st.line_chart(cdf, use_container_width=True)
            m1, m2, m3 = st.columns(3)
            m1.metric("累计收益", utils.pct_text(bt.get("cum_return")))
            m2.metric("最大回撤", utils.pct_text(bt.get("max_drawdown")))
            m3.metric("夏普", f"{bt.get('sharpe'):.2f}" if bt.get("sharpe") is not None else "-")
            if bt.get("bench"):
                st.caption(
                    f"基准 {bt['bench']} 累计 {utils.pct_text(bt.get('bench_cum_return'))}"
                    f" · 超额 {utils.pct_text(bt.get('excess_cum'))}"
                )
            st.caption("统一后复权净值 E3/E14 · 严格时序(禁未来函数)")
with reb_c:
    with ui.panel("再平衡提醒", tag="BR-5.5 · 偏离 ±5% · E8"):
        rb = api_client.get_portfolio_rebalance()
        rating = rb.get("rating", "green")
        if rating == "red":
            st.error("🔴 触发再平衡阈值(偏离 >5% 或 止损红线)")
        elif rating == "yellow":
            st.warning("🟡 关注偏离")
        else:
            st.success("🟢 偏离在阈值内")
        for item in rb.get("rebalance", []):
            st.write(f"- {item.get('action', item.get('dim', ''))}")
        if not rb.get("rebalance"):
            st.caption("当前无需再平衡")
        st.caption("股债偏离 >5% 触发(E8)；相关性矩阵待后端计算")

ui.source_footer()
