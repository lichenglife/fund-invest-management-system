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
        cur_parts = current.split()
        cur_row = cur_parts[0] if len(cur_parts) > 0 else ""
        cur_col = cur_parts[1] if len(cur_parts) > 1 else ""

        # 表头
        hdr = st.columns([1, 1, 1, 1])
        hdr[0].markdown("**市值\\\\风格**")
        for c, name in zip(hdr[1:], _COLS, strict=False):
            c.markdown(f"**{name}**")

        for row in _ROWS:
            cols = st.columns([1, 1, 1, 1])
            cols[0].markdown(f"**{row}**")
            for c, name in zip(cols[1:], _COLS, strict=False):
                is_cur = row == cur_row and name == cur_col
                if is_cur:
                    c.markdown(
                        f'<div style="background:#eaf5f0;border:2px solid #0f9d76;'
                        f"border-radius:6px;padding:8px;text-align:center;font-weight:700;"
                        f'color:#0b7d5c">{row}{name}</div>',
                        unsafe_allow_html=True,
                    )
                else:
                    c.markdown(
                        '<div style="background:#fafbfc;border:1px solid #e3e8ef;'
                        'border-radius:6px;padding:8px;text-align:center;color:#6b7785">'
                        "—</div>",
                        unsafe_allow_html=True,
                    )

        st.caption(f"判定=持仓市值 + 估值成长因子 · 当前定位：**{current}**")
        if cv_ok:
            st.success("回归校验一致 ✅")
        else:
            st.warning("回归校验存在偏差，建议关注")
