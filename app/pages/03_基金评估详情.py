"""基金评估详情(原型③；FR-06~09,45 / DC-003；P1-03a~d + P1-04a/b + P1-14a/b)。

指标卡(区间/基准) · 五因子可解释评分(滑杆重算) · 风格箱 · Brinson 归因 · 研究指标卡。
评估引擎为全站唯一权威源(ADR-002 / BR-2.12)。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from app import api_client, state, utils  # noqa: E402
from app.components import brinson_chart, score_panel, style_box, ui  # noqa: E402
from app.mock import store  # noqa: E402

ui.inject_global_style()
ui.page_header(
    "🔬 基金评估详情", "指标卡(区间/基准) · 五因子可解释评分 · 风格箱 · Brinson 归因 · 研究指标卡"
)

if api_client.is_mock():
    ui.mock_hint()

# 基金选择 + 区间/基准(BR-2.1，基准按类型自动选宽基)
sel_code = state.selected_fund() or "110011"
code = st.selectbox(
    "选择基金",
    [f["code"] for f in store.FUNDS],
    format_func=lambda c: f"{c} · {store.fund_by_code(c)['name']}" if store.fund_by_code(c) else c,
    index=(
        [f["code"] for f in store.FUNDS].index(sel_code)
        if sel_code in [f["code"] for f in store.FUNDS]
        else 0
    ),
)
state.select_fund(code)
fund = store.fund_by_code(code) or store.FUNDS[0]

c_int, c_bench = st.columns(2)
with c_int:
    window = st.selectbox(
        "评估区间（默认滚动 3 年）", ["近 3 年（默认）", "近 1 年", "近 5 年", "成立以来"]
    )
with c_bench:
    bench_auto = {
        "stock": "沪深300（股票型自动）",
        "mix": "中证800（混合型自动）",
        "etf": "沪深300（ETF自动）",
        "bond": "中债总财富（债券型自动）",
        "qdii": "标普500全收益（QDII自动）",
    }.get(fund["type"], "沪深300")
    st.selectbox("基准（按类型自动选宽基，可改）", [bench_auto, "沪深300", "中证800", "中债总财富"])

st.divider()

# --- 核心指标卡(BR-2.1) + 五因子评分 ---
mc, sc = st.columns([1, 1])
with mc:
    with ui.panel("核心指标卡", tag="BR-2.1 · 近3年/沪深300"):
        m = api_client.get_metrics(code)
        if m:
            rows = [
                {
                    "指标": k,
                    "值": (
                        utils.format_pct(v)
                        if k in ("年化收益", "年化波动", "最大回撤")
                        else f"{v:g}"
                    ),
                    "口径": m.get("window", "3y") + "/" + m.get("benchmark", "沪深300"),
                }
                for k, v in m.items()
                if k not in ("window", "benchmark", "cv_error")
            ]
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            err = m.get("cv_error", 0)
            if err < 0.005:
                st.success("开源库(empyrical/statsmodels)交叉验证：误差 <0.5% ✅")
            else:
                st.warning(f"交叉验证误差 {err*100:.2f}% >0.5%，标红存疑")
with sc:
    score = api_client.get_score(code)
    if score:
        score_panel.render(score, allow_tune=True)

# --- 风格箱 + 多基金对比(BR-2.3/2.5) ---
sb, cmp = st.columns([1, 1])
with sb:
    style_box.render(current=fund.get("style", "中盘 成长"), cv_ok=True, manager=False)
with cmp:
    with ui.panel("多基金对比", tag="BR-2.5 · 并排 2~5 只"):
        chosen = st.multiselect(
            "选择对比基金(2~5)",
            [f["code"] for f in store.FUNDS],
            default=["110011", "000961", "161725"],
            format_func=lambda c: store.fund_by_code(c)["name"] if store.fund_by_code(c) else c,
        )
        if chosen:
            cmp_rows = [
                {
                    "代码": c,
                    "名称": store.fund_by_code(c)["name"],
                    "评分": store.fund_by_code(c)["score"],
                }
                for c in chosen
            ]
            st.dataframe(pd.DataFrame(cmp_rows), use_container_width=True, hide_index=True)

st.divider()

# --- Brinson 归因(BR-2.4，仅 mixed/stock) ---
brinson_chart.render(api_client.get_attribution(code), fund_type=fund["type"])

# --- 研究型指标(FR-45，分组卡片+阈值着色+一句话解读；PEG/ERP 走守卫) ---
res = api_client.get_research(code)
with ui.panel("研究型指标", tag="FR-45 · 分组卡片 + 阈值着色 · TP-01 §3.7"):
    items = res.get("items", [])
    cols = st.columns(3) if items else st.columns(1)
    for col, it in zip(cols, items, strict=False):
        with col:
            color = utils.level_color(it["level"])
            st.markdown(
                f'<div style="border:1px solid {color};border-radius:8px;padding:10px 12px;'
                f'background:{"var(--brand-bg)" if it["level"]=="good" else "var(--warn-bg)" if it["level"]=="warn" else "var(--danger-bg)"}">'
                f'<div style="font-size:12px;color:var(--text-muted)">{it["name"]}</div>'
                f'<div style="font-size:18px;font-weight:700;color:{color}">{it["value"]:g}</div>'
                f'<div style="font-size:11px">{it["desc"]}</div></div>',
                unsafe_allow_html=True,
            )
    ui.source_footer(
        extra="交叉验证误差 <0.5%（>0.5% 标红存疑）；未定义口径过 RESEARCH_PROXY_GUARD(40301)"
    )
