"""基金数据中心(原型②；FR-01~05 / DC-002；P1-02a/b + P1-13a/b/c)。

全类型(含 ETF/LOF) + 搜索 + 分类树 + 发现；档案分组+字段解释；
净值复权/下载/盘中估算；持仓跳穿透；经理风格箱。
验证点：全类型检索是否顺手。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from app import api_client, state  # noqa: E402
from app.components import style_box, ui  # noqa: E402
from app.mock import store  # noqa: E402

st.title("🗂️ 基金数据中心")
st.caption("全类型（含 ETF/LOF）· 搜索 + 分类树 + 发现 · 档案字段解释 · 净值复权/下载 · 跳穿透")

if api_client.is_mock():
    ui.mock_hint()

# --- 搜索 + 分类树 + 发现(DC-002 A/B) ---
sc, ct = st.columns([3, 2])
with sc:
    q = st.text_input("搜索（代码 / 拼音 / 名称）", placeholder="如：沪深300ETF、110011、sh300")
    funds = api_client.list_funds()
    if q:
        ql = q.lower()
        funds = [
            f
            for f in funds
            if ql in f["code"].lower()
            or ql in f["name"].lower()
            or ql in str(f.get("theme", "")).lower()
        ]
    if funds:
        df = pd.DataFrame(
            [
                {
                    "代码": f["code"],
                    "名称": f["name"],
                    "类型": store.TYPE_LABELS.get(f["type"], f["type"]),
                    "规模(亿)": f["scale_yi"],
                    "评分": f["score"],
                    "经理": f["manager"],
                }
                for f in funds
            ]
        )
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.caption("无匹配基金")

with ct:
    st.markdown("**分类树**")
    for k, vs in store.CATEGORY_TREE.items():
        with st.expander(f"{k}（{len(vs)}）"):
            st.write(" / ".join(vs))
    st.markdown("**发现入口**")
    for tag in ["🔥 按信号发现", "🏆 按榜单发现", "🎓 按学习推荐"]:
        st.button(tag, key=f"disc_{tag}")

st.divider()

# --- 选中基金详情(DC-002 C~F) ---
code = st.selectbox(
    "选择基金查看档案",
    [f["code"] for f in store.FUNDS],
    format_func=lambda c: f"{c} · {store.fund_by_code(c)['name']}" if store.fund_by_code(c) else c,
    index=0,
)
fund = api_client.get_fund(code)
state.select_fund(code)

tab_arch, tab_nav, tab_hold, tab_mgr = st.tabs(
    ["📋 基金档案", "📈 净值", "🔎 持仓透视", "👤 经理风格箱"]
)

# C. 档案分组 + 字段解释 tooltip(DC-002 C)
with tab_arch:
    if fund:
        g1, g2 = st.columns(2)
        with g1:
            st.markdown("**概览**")
            st.write(f"代码：{fund['code']} · 名称：{fund['name']}")
            st.write(
                f"类型：{store.TYPE_LABELS.get(fund['type'], fund['type'])} / {fund.get('sub_type','-')}"
            )
            st.write(f"主题：{fund.get('theme','-')} · 风格：{fund.get('style','-')}")
            st.write(f"管理人：{fund.get('company','-')} · 成立：{fund.get('launch_date','-')}")
            st.write(f"经理：{fund['manager']} · 任职回报 +{int(fund['tenure_return']*100)}%")
        with g2:
            st.markdown("**费率 / 规模 / 风险**")
            st.write(f"费率：{fund['fee_rate']*100:.2f}%")
            st.write(f"规模：{fund['scale_yi']:.2f} 亿")
            st.markdown("**字段解释**（hover 看释义）")
            st.markdown(
                "跟踪误差" + ui.tooltip("", "基金收益与基准偏离的波动率，越低越贴合指数") + " · "
                "最大回撤" + ui.tooltip("", "历史最高点到最低点的最大跌幅，衡量极端风险") + " · "
                "Sharpe" + ui.tooltip("", "每单位波动带来的超额收益，越高越好"),
                unsafe_allow_html=True,
            )

# D. 净值复权 + 下载 + 盘中估算(DC-002 D，后复权净值 E3/E14)
with tab_nav:
    nv = ["单位净值", "累计净值", "复权净值"]
    sel = st.radio("净值类型", nv, horizontal=True, label_visibility="collapsed")
    st.caption(f"当前展示：{sel}（回测统一用复权净值，杜绝分红双重计 E3/E14）")
    navs = api_client.get_nav(code, days=120)
    ndf = pd.DataFrame(navs)
    col_map = {"单位净值": "nav", "累计净值": "acc_nav", "复权净值": "adj_nav"}
    series = ndf.set_index("trade_date")[[col_map[sel]]]
    st.line_chart(series, use_container_width=True)
    st.download_button(
        "⬇ 下载 CSV / Excel",
        ndf.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"{code}_nav.csv",
        mime="text/csv",
    )
    est = store.INTRADAY_ESTIMATE
    st.info(
        f"盘中估算：+{est['estimate_pct']*100:.2f}% · 估算净值 {est['estimate_nav']}（仅供参考，以收盘净值为准）"
    )

# E. 持仓透视 -> 跳穿透(DC-002 E)
with tab_hold:
    holdings = api_client.get_holdings(code)
    if holdings:
        st.markdown("**前十大重仓股**（按占净值比排序）")
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
                for h in holdings
            ]
        )
        st.dataframe(hdf, use_container_width=True, hide_index=True)
        st.markdown("**行业分布**")
        idf = pd.DataFrame(api_client.get_penetrate(code)["industry"])
        st.bar_chart(idf.set_index("industry"), use_container_width=True)
        st.page_link(
            "pages/09_持仓穿透舆情.py", label="🔎 点击跳转「持仓穿透与舆情」看舆情与财务", icon="➡️"
        )
    else:
        st.caption("暂无持仓披露")

# F. 经理风格箱(DC-002 F)
with tab_mgr:
    style_box.render(current=fund.get("style", "中盘 成长"), cv_ok=True, manager=True)
    if fund:
        st.caption(
            f"当前经理：{fund['manager']} · 任职回报 +{int(fund['tenure_return']*100)}% · 代表基 {fund['code']}"
        )

ui.source_footer()
