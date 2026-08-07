"""components.kpi_card · 圆角白底 KPI 指标卡(原型① FR-D1；可复用)。

四分区：标签 / 数值 / 周期 / 涨跌幅(delta)。涨跌幅颜色按全局语义：红涨绿跌
(A股惯例，正=红、负=绿)。纯展示控件，入参明确，不依赖页面级 ``st.session_state``。

样式类(.fl-kpi-card/.fl-kpi-value/.fl-kpi-period/.fl-kpi-delta)定义于
``app/static/style.css``，由 ``ui.inject_global_style`` 注入生效。
"""

from __future__ import annotations

import streamlit as st

from app import utils


def _escape(text: str) -> str:
    """转义受控文本尖括号(§9 安全；防注入)。"""
    return str(text).replace("<", "&lt;").replace(">", "&gt;")


def kpi_card_html(
    label: str,
    value: str,
    period: str | None = None,
    delta: str | None = None,
    is_positive: bool = True,
) -> str:
    """返回 KPI 卡 HTML 字符串(令牌 v2 · 可在 .fl-grid 中拼接多卡后统一渲染)。

    与 ``kpi_card`` 视觉完全一致；抽离 HTML 以便 ``ui.kpi_grid`` 在单个网格容器内
    拼接多张卡，实现按容器宽度的 auto-fit 回流(CR-20260806-01 移动优先)。
    """
    cls = "pos" if is_positive else "neg"
    period_html = f'<div class="fl-kpi-period">{_escape(period)}</div>' if period else ""
    delta_html = ""
    if delta:
        delta_html = f'<div class="fl-kpi-delta {cls}">{utils.pct_text(float(delta)) if _is_num(delta) else _escape(delta)}</div>'
    return (
        f'<div class="fl-kpi-card">'
        f'<div class="fl-kpi-label">{_escape(label)}</div>'
        f'<div class="fl-kpi-value {cls}">{_escape(value)}</div>'
        f"{period_html}{delta_html}"
        f"</div>"
    )


def kpi_card(
    label: str,
    value: str,
    period: str | None = None,
    delta: str | None = None,
    is_positive: bool = True,
) -> None:
    """渲染圆角白底 KPI 指标卡。

    Args:
        label: 卡片标签(如「模拟组合收益」)。
        value: 主数值(已格式化字符串，如「+12.40%」)。
        period: 周期小标签(如「近一年」)；None 不显示。
        delta: 涨跌幅文本(如「+1.2%」)；None 不显示。颜色由 ``is_positive`` 决定。
        is_positive: True 数值/涨跌幅用红(涨/正收益，红涨绿跌)，False 绿(跌/负收益)。
    """
    st.markdown(
        kpi_card_html(label, value, period, delta, is_positive),
        unsafe_allow_html=True,
    )


def _is_num(s: str) -> bool:
    """判断字符串是否可解析为数值(决定 delta 是否走 pct_text 着色)。"""
    try:
        float(s)  # noqa: F841
        return True
    except (TypeError, ValueError):
        return False


__all__ = ["kpi_card", "kpi_card_html"]
