"""模拟交易(原型⑤；FR-15~19 / DC-005；P1-07a~e + P1-16a/b)。

100万虚拟资金 · T 日收盘净值成交(非交易时段顺延) · 持仓看板(亏损联动回本)
· 历史定投回测 · 复盘笔记。账户可重置(二次确认)，不连通实盘(§10 非目标)。
盈亏用复权净值(E3/E14)。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from app import api_client, state, utils  # noqa: E402
from app.components import ui  # noqa: E402
from app.mock import store  # noqa: E402

st.title("💰 模拟交易")
st.caption("100万虚拟资金 · T 日收盘净值成交 · 历史定投回测 · 复盘联动回本（不连通实盘）")

if api_client.is_mock():
    ui.mock_hint()


def _price(code: str) -> float:
    """当前后复权净值(取净值序列末值；真实由后端 T 日收盘给)。"""
    navs = store.nav_series(code, days=30)
    return float(navs[-1]["adj_nav"]) if navs else 1.0


def _recompute() -> None:
    """由持仓重算市值/收益(本地记账核心)。"""
    acct = state.paper_account()
    positions = state.paper_positions()
    mv = 0.0
    for p in positions:
        price = _price(p["code"])
        p["market_value"] = round(p["shares"] * price, 2)
        p["return_pct"] = (p["market_value"] / p["cost"] - 1) if p["cost"] else 0.0
        mv += p["market_value"]
    acct["market_value"] = round(mv, 2)
    acct["total_return"] = (acct["cash"] + mv) / acct["init_capital"] - 1
    acct["total_assets"] = round(acct["cash"] + mv, 2)


_recompute()
acct = state.paper_account()

# --- 账户四卡(BR-4.1) ---
ui.metric_row(
    [
        {"k": "虚拟资金", "v": f"{acct['init_capital']:,.0f}", "color": utils.COLOR_GRAY},
        {"k": "可用", "v": utils.format_amount(acct["cash"]), "color": utils.COLOR_BLUE},
        {
            "k": "持仓市值",
            "v": utils.format_amount(acct["market_value"]),
            "color": utils.COLOR_GREEN,
        },
        {
            "k": "总收益",
            "v": utils.pct_text(acct["total_return"]),
            "color": utils.pct_color(acct["total_return"]),
        },
    ]
)

st.divider()

# --- 买入/卖出(BR-4.2，T 日收盘净值成交) + 持仓看板(BR-4.3) ---
trade_c, pos_c = st.columns([1, 2])
with trade_c:
    with ui.panel("买入 / 卖出", tag="BR-4.2 · T 日收盘净值成交"):
        code = st.selectbox(
            "基金代码",
            [f["code"] for f in store.FUNDS],
            format_func=lambda c: (
                f"{c} · {store.fund_by_code(c)['name']}" if store.fund_by_code(c) else c
            ),
        )
        side = st.segmented_control("方向", ["买入", "卖出"], default="买入")
        amount = st.number_input("金额(元)", min_value=100, value=50000, step=10000)
        note = st.text_area("买入逻辑（复盘用 · BR-4.5）", placeholder="如：估值低位，定投加仓")
        price = _price(code)
        st.caption(f"当前后复权净值：{price:.4f} · 预计份额 {amount/price:,.2f}")
        if st.button(f"模拟{side}", type="primary"):
            if side == "买入":
                if amount > acct["cash"]:
                    st.error("可用资金不足")
                else:
                    shares = amount / price
                    acct["cash"] = round(acct["cash"] - amount, 2)
                    pos = next((p for p in state.paper_positions() if p["code"] == code), None)
                    if pos:
                        pos["cost"] = round(pos["cost"] + amount, 2)
                        pos["shares"] = round(pos["shares"] + shares, 4)
                        pos["cost_price"] = pos["cost"] / pos["shares"]
                    else:
                        f0 = store.fund_by_code(code)
                        state.paper_positions().append(
                            {
                                "code": code,
                                "name": f0["name"] if f0 else code,
                                "cost": float(amount),
                                "shares": round(shares, 4),
                                "cost_price": price,
                                "market_value": float(amount),
                                "return_pct": 0.0,
                                "bench_diff": 0.0,
                            }
                        )
                    state.paper_trades().append(
                        {"side": "buy", "code": code, "amount": amount, "note": note}
                    )
                    st.success(
                        f"已模拟买入 {code} {amount:,.0f}元（非交易时段顺延下一交易日，BR-4.2）"
                    )
                    st.rerun()
            else:  # 卖出
                pos = next((p for p in state.paper_positions() if p["code"] == code), None)
                if not pos:
                    st.error("无该基金持仓")
                elif amount > pos["market_value"]:
                    st.error("卖出金额超过持仓市值")
                else:
                    shares = amount / price
                    pos["shares"] = round(pos["shares"] - shares, 4)
                    pos["cost"] = round(
                        pos["cost"] * max(pos["shares"], 0) / (pos["shares"] + shares), 2
                    )
                    acct["cash"] = round(acct["cash"] + amount, 2)
                    if pos["shares"] <= 0.0001:
                        state.paper_positions()[:] = [
                            p for p in state.paper_positions() if p["code"] != code
                        ]
                    state.paper_trades().append(
                        {"side": "sell", "code": code, "amount": amount, "note": note}
                    )
                    st.success(f"已模拟卖出 {code} {amount:,.0f}元")
                    st.rerun()
        st.caption("⚙ 账户可重置清零，不连通任何实盘(BR-4.1)")

with pos_c:
    with ui.panel("持仓看板", tag="BR-4.3 · 盈亏用复权净值"):
        positions = state.paper_positions()
        if positions:
            pdf = pd.DataFrame(
                [
                    {
                        "基金": p["code"],
                        "成本": f"{p['cost']:,.0f}",
                        "市值": f"{p['market_value']:,.0f}",
                        "盈亏": utils.pct_text(p["return_pct"]),
                        "基准对照": f"{'跑赢' if p.get('bench_diff',0)>=0 else '跑输'} {abs(p.get('bench_diff',0))*100:.1f}%",
                    }
                    for p in positions
                ]
            )
            st.dataframe(pdf, use_container_width=True, hide_index=True)
            # 亏损联动回本(BR-4.5 联动 FR-40)
            for p in positions:
                if p["return_pct"] < -0.10:
                    need = utils.breakeven_need(p["return_pct"])
                    st.error(
                        f"🔴 {p['code']} 亏损 {p['return_pct']*100:.1f}% -> 回本需涨 +{need*100:.1f}% "
                        f"👉 "
                    )
                    st.page_link("pages/08_单基深度实验室.py", label="前往单基实验室测算", icon="➡️")
                    break
        else:
            st.caption("暂无持仓，去买入试试")
        st.caption("盈亏用复权净值计算 · 基准：沪深300")

st.divider()

# --- 历史定投回测(BR-4.4) + 复盘笔记(BR-4.5/4.6) ---
dca_c, note_c = st.columns(2)
with dca_c:
    with ui.panel("历史定投回测", tag="BR-4.4 · 区间 ≥1 年真实回放"):
        dca = api_client.get_dca_backtest()
        st.write(f"标的：{dca['code']} · {dca['freq']} · {dca['amount']}元 · {dca['period']}")
        if st.button("回放定投"):
            st.info(
                f"定投收益曲线：累计投入 {utils.format_amount(dca['invested'])} / "
                f"市值 {utils.format_amount(dca['market_value'])} / "
                f"收益 {utils.pct_text(dca['return_pct'])} / 成本摊薄显著"
            )
with note_c:
    with ui.panel("交易复盘与笔记", tag="BR-4.5/4.6"):
        trades = state.paper_trades()
        if trades:
            st.dataframe(pd.DataFrame(trades), use_container_width=True, hide_index=True)
        else:
            st.caption("暂无交易记录")
        st.caption("每笔记录买卖理由+结果；亏损自动提示回本并链接实验室")

# --- 重置二次确认(FR-15/DC-005) ---
st.divider()
with st.expander("⚙ 账户管理"):
    if st.button("重置模拟账户", type="secondary"):
        st.session_state["_confirm_reset"] = True
    if st.session_state.get("_confirm_reset"):
        st.warning("确认清零所有持仓与交易记录？此操作不可撤销。")
        c1, c2 = st.columns(2)
        if c1.button("确认重置", type="primary"):
            state.reset_paper()
            st.session_state.pop("_confirm_reset", None)
            st.success("账户已重置")
            st.rerun()
        if c2.button("取消"):
            st.session_state.pop("_confirm_reset", None)
            st.rerun()

ui.source_footer()
