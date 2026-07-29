"""持仓穿透与舆情(原型⑨；FR-43,44 / DC-012；P3-01a/b + P3-02a/b)。

前十大重仓股(来源+时间，按占净值比排序) · 四维度财务卡(增速/毛利/现金流/杠杆)
· 舆情周评(AI 统一出口)。持仓季更 / 舆情日更 / 进入自动穿透+手动刷新(BR-11.6)。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from app import api_client, utils  # noqa: E402
from app.components import ui  # noqa: E402
from app.mock import store  # noqa: E402

st.title("🔎 持仓穿透舆情")
st.caption("前十大(来源+时间，按占净值比排序) · 四维度财务卡 · 舆情周评(AI 统一出口)")

if api_client.is_mock():
    ui.mock_hint()

code = st.selectbox(
    "选择基金",
    [f["code"] for f in store.FUNDS],
    format_func=lambda c: f"{c} · {store.fund_by_code(c)['name']}" if store.fund_by_code(c) else c,
    index=0,
)
pen = api_client.get_penetrate(code)

if st.button("🔄 手动刷新舆情"):
    st.success("舆情已刷新（持仓季更 · 舆情日更 · 进入基金自动触发穿透 BR-11.6）")

# --- 前十大重仓股(BR-11.1，带舆情/来源/时间) ---
with ui.panel("前十大重仓股", tag="BR-11.1 · 按占净值比排序"):
    if pen["holdings"]:
        hdf = pd.DataFrame(
            [
                {
                    "股票": h["stock_name"],
                    "代码": h["stock_code"],
                    "占净值": f"{h['weight']*100:.1f}%",
                    "舆情": h["sentiment"],
                    "来源": h["source"],
                    "时间": h["date"],
                }
                for h in pen["holdings"]
            ]
        )
        st.dataframe(hdf, use_container_width=True, hide_index=True)
    else:
        st.caption("暂无持仓披露")

# --- 四维度财务卡(FR-44/BR-11.3) + 舆情周评(FR-43/BR-11.4) ---
fin_c, wk_c = st.columns(2)
with fin_c:
    with ui.panel("重仓股财务透视", tag="FR-44/BR-11.3 · 四维度"):
        fin = pen["financials"].get("600519", [])
        cols = st.columns(len(fin)) if fin else st.columns(1)
        for col, f in zip(cols, fin, strict=False):
            with col:
                color = utils.level_color(f["level"])
                st.markdown(
                    f'<div style="border:1px solid {color};border-radius:6px;padding:8px 10px;'
                    f'text-align:center"><div style="font-size:11px;color:#6b7785">{f["dim"]}</div>'
                    f'<div style="font-size:16px;font-weight:700;color:{color}">{f["value"]}</div>'
                    f'<div style="font-size:10px">{f["desc"]}</div></div>',
                    unsafe_allow_html=True,
                )
        st.caption("来源：Tushare · 截至 2025-Q1（季更）")
with wk_c:
    with ui.panel("舆情周评", tag="FR-43/BR-11.4 · AI 周报统一出口"):
        st.info(pen["sentiment_weekly"] or "暂无周评")
        ui.source_footer(source="新闻聚合")

ui.source_footer(extra="持仓季更 / 舆情日更")
