"""components.ui · 通用复合控件(开发规范§2.2/§10.2)。

跨页复用的展示控件：指标卡 / 面板 / 状态药丸 / 来源页脚 / 折叠区 / 示例角标。
封装原型 .card/.panel/.pill/.source/.fold 的视觉口径(原型§5 设计令牌)。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit as st

from app.utils import LEVEL_COLOR, level_emoji, level_row, tooltip

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
    """指标卡(原型 .card；k/v 结构，带颜色)。色值对齐 static/style.css 令牌。"""
    if color:
        st.markdown(
            f'<div style="border:1px solid #E5E7EB;border-radius:12px;padding:12px;'
            f'box-shadow:0 1px 3px rgba(0,0,0,0.08)">'
            f'<div style="color:#6B7280;font-size:12px">{label}</div>'
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
            hdr += f" <small style='color:#6B7280'>· {tag}</small>"
        st.markdown(hdr, unsafe_allow_html=True)
    return st.container(border=border)


def status_pill(level: str, text: str | None = None) -> str:
    """状态药丸(原型 .pill)：返回带背景色的内联 markdown。

    色值对齐 static/style.css 令牌：good 用浅绿底品牌绿字、warn 浅黄、bad 浅红。
    红(#FDE8E8)仅用于 bad 风险药丸，不用于 active/selected。
    """
    color = LEVEL_COLOR.get(level, "#6B7280")
    bg = {
        "good": "#F0FDF4",
        "ok": "#F0FDF4",
        "warn": "#FEF9C3",
        "bad": "#FDE8E8",
        "g": "#F0FDF4",
        "y": "#FEF9C3",
        "r": "#FDE8E8",
    }.get(level, "#F3F4F6")
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


def warning_banner(text: str, key: str, icon: str = "⚠️") -> None:
    """独立 warning 卡片：浅黄底 + 左侧图标 + 正文 + 关闭按钮(原型① 顶部提示)。

    图标与文字垂直居中(flex align-center)；关闭按钮写 session_state，
    点击后整条隐藏(刷新可复现)。``key`` 隔离多条 banner 的关闭状态。
    """
    dismiss_key = f"_dismiss_banner_{key}"
    if st.session_state.get(dismiss_key):
        return
    text = str(text).replace("<", "&lt;").replace(">", "&gt;")
    col_text, col_btn = st.columns([22, 1])
    with col_text:
        st.markdown(
            f'<div class="fl-warning-banner">'
            f'<span class="fl-wb-icon">{icon}</span>'
            f'<span class="fl-wb-text">{text}</span>'
            f"</div>",
            unsafe_allow_html=True,
        )
    with col_btn:
        st.button(
            "✕",
            key=f"close_{key}",
            help="关闭提示",
            on_click=lambda: st.session_state.update({dismiss_key: True}),
        )


def kpi_card(label: str, value: str, period: str | None = None, positive: bool = True) -> None:
    """圆角白底 KPI 卡(原型① FR-D1)：标签 + 数值(正绿负红) + 周期小标签。

    ``positive`` 控制数值色：True 翠绿(收益为正)、False 红(亏损/跑输，金融语义)。
    """
    cls = "pos" if positive else "neg"
    period_html = f'<div class="fl-kpi-period">{period}</div>' if period else ""
    st.markdown(
        f'<div class="fl-kpi-card">'
        f'<div class="fl-kpi-label">{label}</div>'
        f'<div class="fl-kpi-value {cls}">{value}</div>'
        f"{period_html}"
        f"</div>",
        unsafe_allow_html=True,
    )


_CSS_PATH = Path(__file__).resolve().parent.parent / "static" / "style.css"


def _load_css() -> str:
    """读取 static/style.css(设计令牌单一权威源)。

    失败时回退最小内联样式(布局不崩)，并记日志；正常路径下 CSS 集中管理于
    ``app/static/style.css``，便于审校与主题维护。
    """
    try:
        return _CSS_PATH.read_text(encoding="utf-8")
    except OSError as exc:  # pragma: no cover - 取决于部署
        import logging

        logging.getLogger(__name__).warning("style.css 加载失败: %s", exc)
        return "/* style.css 丢失，回退最小布局 */\n.block-container{max-width:100%!important}"


def inject_global_style() -> None:
    """全局布局与视觉 CSS(原型§5 翠绿专业风设计令牌)。

    Streamlit 多页应用中各页为独立脚本，需在各页面顶部调用一次使布局全局生效。
    CSS 集中于 ``app/static/style.css``(设计令牌权威源)，此处读取并注入
    ``<style>`` 块；令牌含品牌墨绿/翠绿、卡片阴影圆角 12px、sidebar 品牌区与
    active 品牌绿高亮(禁用红色作选中态)。
    """
    st.markdown(f"<style>{_load_css()}</style>", unsafe_allow_html=True)


def page_header(title: str, subtitle: str = "") -> None:
    """页面统一表头(原型§2 顶部信息架构)：翠绿色带 + 标题 + 副标题。

    替代裸 st.title，增强视觉层次与品牌一致性。各页顶部调用。
    """
    sub_html = f'<div class="fl-sub">{subtitle}</div>' if subtitle else ""
    st.markdown(
        f'<div class="fl-page-header"><div class="fl-title">{title}</div>{sub_html}</div>',
        unsafe_allow_html=True,
    )


def df_with_style(df: Any, use_container_width: bool = True) -> None:
    """统一表格展示(原型 table 样式)。"""
    st.dataframe(df, use_container_width=use_container_width, hide_index=True)


__all__ = [
    "LEVEL_LABEL",
    "metric_card",
    "metric_row",
    "panel",
    "status_pill",
    "source_footer",
    "fold",
    "mock_hint",
    "warning_banner",
    "kpi_card",
    "df_with_style",
    "level_row",
    "tooltip",
    "level_emoji",
    "inject_global_style",
    "page_header",
]
