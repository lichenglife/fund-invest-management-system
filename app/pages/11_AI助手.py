"""AI 助手(原型⑪；FR-29~32 / DC-008；P3-03a/b + P3-04a/b)。

RAG 检索增强对话(来源+截至+拒答) · 周报 · 持仓舆情周评(统一出口) · 失败降级。
所有 AI 输出标注 来源+截至+「仅供参考，不构成投资建议」(FR-46)。
依赖 LLM key(TP-06 R7)；无依据拒答(§3.11.7)。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st  # noqa: E402

from app import api_client  # noqa: E402
from app.components import ui  # noqa: E402

ui.inject_global_style()
ui.page_header("🤖 AI 助手", "RAG 检索增强 · 无依据拒答 · 持仓舆情周评 · 失败降级（FR-29~32）")

if api_client.is_mock():
    ui.mock_hint()

ai = api_client.get_ai_demo()

# --- 快捷指令 ---
st.markdown("**快捷指令**")
qc_cols = st.columns(len(ai["quick"]))
for col, cmd in zip(qc_cols, ai["quick"], strict=False):
    col.button(cmd, key=f"qc_{cmd}")

st.divider()

# --- 对话窗(含无依据拒答样例 · BR-7.x) ---
with ui.panel("对话", tag="§3.11.7 RAG · 来源+拒答", border=True):
    # 演示对话历史(真实由后端 RAG 问答接口提供)
    for msg in ai["chat"]:
        if msg["role"] == "user":
            st.chat_message("user").write(msg["text"])
        else:
            with st.chat_message("assistant"):
                st.write(msg["text"])
                if msg.get("source"):
                    if msg.get("reject"):
                        st.error(msg["source"])
                    else:
                        st.caption(msg["source"])
    # 用户输入(演示：回显样例拒答)
    if user_q := st.chat_input("问我关于基金/组合/舆情的问题…"):
        st.chat_message("user").write(user_q)
        with st.chat_message("assistant"):
            st.write("（示例）我可基于持仓/舆情给你「当前状态」与可解释分析，但不做确定性预测。")
            st.caption("无依据拒答(§3.11.7) · 来源：RAG 检索 · 截至 2025-07-20 · 仅供参考")

st.divider()

# --- 持仓舆情周评(统一出口 · BR-7.7) + 失败降级(BR-7.8) ---
wk_c, dg_c = st.columns(2)
with wk_c:
    with ui.panel("持仓舆情周评", tag="BR-7.7 · 统一出口"):
        st.info(ai["weekly"])
with dg_c:
    with ui.panel("失败降级", tag="BR-7.8 · 不阻塞主流程"):
        st.warning(ai["degrade"])

st.caption(
    "所有 AI 输出标注数据来源 + 截至时间 +「仅供参考，不构成投资建议」(FR-46)；"
    "周报默认每周一自动生成(BR-7.4)"
)
