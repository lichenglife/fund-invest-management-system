"""components.ui · 通用复合控件(开发规范§2.2/§10.2)。

跨页复用的展示控件：指标卡 / 面板 / 状态药丸 / 来源页脚 / 折叠区 / 示例角标。
封装原型 .card/.panel/.pill/.source/.fold 的视觉口径(原型§5 设计令牌)。
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from app.utils import LEVEL_COLOR, level_emoji

#: level -> 中文标签(原型 .pill ok/warn/bad)。
LEVEL_LABEL = {
    "good": "正面",
    "ok": "安全",
    "warn": "中性",
    "bad": "负面",
    "g": "均衡",
    "y": "偏低",
    "r": "风险",
}


def metric_card(label: str, value: str, color: str | None = None) -> None:
    """指标卡(原型 .card；k/v 结构，带颜色)。"""
    if color:
        st.markdown(
            f'<div style="border:1px solid #e3e8ef;border-radius:8px;padding:12px;'
            f'box-shadow:0 1px 3px rgba(0,0,0,.04)">'
            f'<div style="color:#6b7785;font-size:12px">{label}</div>'
            f'<div style="font-size:22px;font-weight:700;margin-top:4px;color:{color}">{value}</div>'
            f"</div>",
            unsafe_allow_html=True,
        )
    else:
        st.metric(label, value)


def metric_row(cards: list[dict[str, Any]]) -> None:
    """一行多卡(原型 .cards grid 4 列)。"""
    cols = st.columns(len(cards)) if cards else st.columns(1)
    for col, c in zip(cols, cards, strict=False):
        with col:
            metric_card(c.get("k", ""), str(c.get("v", "-")), c.get("color"))


def panel(title: str, tag: str | None = None, border: bool = True) -> Any:
    """带标题的面板容器(原型 .panel h3)。返回可 ``with`` 的容器。

    tag 显示在标题右侧的小标签(原型 .tag，如「引擎唯一权威源 FR-07」)。
    """
    if title:
        hdr = f"**{title}**"
        if tag:
            hdr += f" <small style='color:#6b7785'>· {tag}</small>"
        st.markdown(hdr, unsafe_allow_html=True)
    return st.container(border=border)


def status_pill(level: str, text: str | None = None) -> str:
    """状态药丸(原型 .pill)：返回带背景色的内联 markdown。"""
    color = LEVEL_COLOR.get(level, "#6b7785")
    bg = {
        "good": "#e7f6ee",
        "ok": "#e7f6ee",
        "warn": "#fff4e0",
        "bad": "#fde8e8",
        "g": "#e7f6ee",
        "y": "#fff4e0",
        "r": "#fde8e8",
    }.get(level, "#eef2f6")
    label = text or LEVEL_LABEL.get(level, level)
    return (
        f'<span style="background:{bg};color:{color};padding:2px 8px;'
        f'border-radius:10px;font-size:11px;font-weight:600">{label}</span>'
    )


def source_footer(
    source: str = "AkShare/Tushare", as_of: str = "2025-07-20", extra: str | None = None
) -> None:
    """来源页脚(原型 .source；溯源+截至+交叉验证)。"""
    parts = [f"来源：{source} · 截至 {as_of}"]
    if extra:
        parts.append(extra)
    st.caption(" · ".join(parts))


def fold(title: str, body_md: str) -> None:
    """折叠次要区(原型 .fold details)。"""
    with st.expander(title):
        st.markdown(body_md)


def mock_hint() -> None:
    """示例数据提示(后端未就绪时页面顶部)。"""
    st.info("🏗️ 当前为示例数据 · 对应后端接口待实现（开发计划 P1/P2/P3）")


def df_with_style(df: Any, use_container_width: bool = True) -> None:
    """统一表格展示(原型 table 样式)。"""
    st.dataframe(df, use_container_width=use_container_width, hide_index=True)


def level_row(level: str) -> str:
    """诊断状态列文本(原型⑥ diag-r/y/g)。"""
    return f"{level_emoji(level)} {LEVEL_LABEL.get(level, '')}"
