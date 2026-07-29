"""宏观市场看板(原型⑦；FR-38,39 / DC-010；P2-01a/b + P2-02a/b)。

宏观卡 + 情绪仪 + 外围传导 · 高位四维排查 · 股债中枢建议。
口径红线(CLAUDE.md §4 E10/E11)：ERP 拆大/小盘加权(7:3)；估值分位固定近10年窗口。
高位排查与风险模块共享同一引擎(FR-38)。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from app import api_client, utils  # noqa: E402
from app.components import ui  # noqa: E402

st.title("🌐 宏观市场认知底盘")
st.caption("先定仓位中枢再选基金（FR-38/39）· 验证点：宏观是否易懂可落地为仓位")

if api_client.is_mock():
    ui.mock_hint()

macro = api_client.get_macro()

# --- 宏观卡(4 卡) ---
ui.metric_row(macro["cards"])

st.divider()

# --- 情绪仪 + 外围传导(BR-9.2/9.3) ---
se, sur = st.columns(2)
with se:
    with ui.panel("市场情绪仪", tag="BR-9.2"):
        st.write("VIX / 成交量 / 融资余额 / 南北向资金 / ETF 申赎")
        st.metric("情绪", macro["sentiment"])
with sur:
    with ui.panel("外围传导", tag="BR-9.3 · 隔夜 -> 次日开盘研判"):
        s = macro["surround"]
        st.write(
            f"🇺🇸 隔夜美股：纳指 {utils.pct_text(s['us_nasdaq'])} · "
            f"中概股 {utils.pct_text(s['china_concept'])} · "
            f"A50 期货 {utils.pct_text(s['a50_future'])}"
        )
        st.info(f"-> {s['judgment']}（非交易时段标「暂无」）")

st.divider()

# --- 高位信号排查(四维 -> 阶段 + 操作暗示 · FR-38/DC-010) + 股债中枢(BR-9.5) ---
hs, pos = st.columns(2)
with hs:
    with ui.panel("高位信号排查", tag="FR-38 · 四维 -> 阶段 + 操作暗示"):
        hsig = macro["high_signal"]
        for h in hsig:
            st.markdown(
                f"- **{h['dim']}** " + ui.status_pill(h["level"], h["signal"]),
                unsafe_allow_html=True,
            )
        st.success(f"综合：{macro['high_verdict']}")
        st.caption("与风险模块共享同一高位引擎(FR-38)")
with pos:
    with ui.panel("股债中枢建议", tag="BR-9.5 · 先定仓位"):
        p = macro["position"]
        st.write(f"沪深300 PE 分位 **{p['pe_pct']*100:.0f}%** -> 股债 **60/40（偏股）**")
        st.write(p["advice"])
        st.page_link("pages/06_组合与配置.py", label="👉 跳转组合与配置 落实仓位", icon="➡️")
        ui.fold(
            "展开其他宏观指标（PPI/GDP）",
            "PPI -2.1% · GDP 同比 +5.0%（数据截至 2025-06，月度 T+15）",
        )

ui.source_footer(
    source="国家统计局/AkShare",
    as_of="2025-06",
    extra="ERP 拆大/小盘加权 7:3(E10)；估值分位近10年窗口(E11)",
)
