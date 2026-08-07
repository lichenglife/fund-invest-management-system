"""components.style_box · 九宫格风格箱(原型③⑥；BR-2.3/DC-002 F)。

判定=持仓市值 + 估值成长因子，并用历史收益回归交叉验证。
九宫格：大盘/中盘/小盘 × 价值/平衡/成长。当前定位高亮，回归校验标注。
"""

from __future__ import annotations

import streamlit as st

from app.components.ui import panel

#: 行=市值(大/中/小)，列=风格(价值/平衡/成长)。
_ROWS = ["大盘", "中盘", "小盘"]
_COLS = ["价值", "平衡", "成长"]


def _matches_current(row: str, col: str, current: str) -> bool:
    """当前定位 token 是否命中「行市值+列风格」格(原型③⑥ 九宫格高亮)。

    用子串匹配，兼容 ``中盘成长``(无空格，store.FUNDS 取值)与 ``中盘 成长``(带空格，
    页面默认传参)两种写法；避免 ``split()`` 把无空格 token 当成单元素、cur_row 取到
    整串而 cur_col 为空，导致当前格永不高亮。
    """
    return bool(row) and bool(col) and row in current and col in current


def render(current: str = "中盘成长", cv_ok: bool = True, manager: bool = False) -> None:
    """渲染九宫格风格箱。

    Args:
        current: 当前定位如「中盘成长」(空格分隔市值与风格)。
        cv_ok: 回归交叉验证是否一致(原型③ ✅)。
        manager: True=经理风格箱(DC-002 F)；False=基金风格箱(BR-2.3)。
    """
    title = "基金经理风格箱" if manager else "风格箱"
    tag = "DC-002 F" if manager else "BR-2.3 · 持仓+回归交叉验证"
    with panel(title, tag=tag):
        # 当前格定位用 _matches_current 子串匹配(见该函数)，无需 split 解析。

        # 表头
        hdr = st.columns([1, 1, 1, 1])
        hdr[0].markdown("**市值\\\\风格**")
        for c, name in zip(hdr[1:], _COLS, strict=False):
            c.markdown(f"**{name}**")

        for row in _ROWS:
            cols = st.columns([1, 1, 1, 1])
            cols[0].markdown(f"**{row}**")
            for c, name in zip(cols[1:], _COLS, strict=False):
                is_cur = _matches_current(row, name, current)
                if is_cur:
                    c.markdown(
                        f'<div style="background:var(--brand-bg);border:2px solid var(--brand);'
                        f"border-radius:6px;padding:8px;text-align:center;font-weight:700;"
                        f'color:var(--brand-deep)">{row}{name}</div>',
                        unsafe_allow_html=True,
                    )
                else:
                    c.markdown(
                        '<div style="background:var(--surface-2);border:1px solid var(--card-border);'
                        'border-radius:6px;padding:8px;text-align:center;color:var(--text-muted)">'
                        "—</div>",
                        unsafe_allow_html=True,
                    )

        st.caption(f"判定=持仓市值 + 估值成长因子 · 当前定位：**{current}**")
        if cv_ok:
            st.success("回归校验一致 ✅")
        else:
            st.warning("回归校验存在偏差，建议关注")
