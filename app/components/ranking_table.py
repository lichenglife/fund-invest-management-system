"""components.ranking_table · 榜单表格封装(原型① FR-D2；可复用)。

封装 ``st.dataframe`` 的列宽/表头/容器样式与「数据截至 + 示例数据」badge 工具栏。
纯展示控件，入参明确，不依赖页面级 ``st.session_state``。

样式类(.fl-table-toolbar/.fl-badge/.stDataFrame 容器)定义于
``app/static/style.css``，由 ``ui.inject_global_style`` 注入生效。

> 注：Streamlit 1.41 的 ``st.dataframe`` 为 canvas 网格，行级斑马纹/hover
> 无法作用于 canvas；容器圆角阴影与表头由 CSS 统一，列宽由 ``column_config`` 控制。
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from app import utils


def _esc(text: str) -> str:
    """转义受控文本尖括号(§9 安全)。"""
    return str(text).replace("<", "&lt;").replace(">", "&gt;")


def ranking_table(
    df: pd.DataFrame,
    columns_config: dict[str, Any] | None = None,
    height: int = 400,
    *,
    as_of: str | None = None,
    mock: bool = False,
    caption: str | None = None,
) -> None:
    """渲染榜单表格(封装 st.dataframe + 列宽 + 表头 + badge 工具栏)。

    Args:
        df: 待展示 DataFrame(已含列名)。
        columns_config: ``st.column_config`` 字典，控制列类型/列宽；None 用默认。
        height: 表格高度(px)。
        as_of: 数据截至日期；非空则在右上角显示 badge。
        mock: True 显示「示例数据」badge。
        caption: 表格下方说明(如评分口径)；None 不显示。
    """
    # 顶部右侧 badge 工具栏
    badges: list[str] = []
    if as_of:
        badges.append(f'<span class="fl-badge as-of">数据截至 {_esc(as_of)}</span>')
    if mock:
        badges.append(f'<span class="fl-badge mock">{_esc(utils.mock_badge())}</span>')
    if badges:
        st.markdown(
            f'<div class="fl-table-toolbar">{"".join(badges)}</div>',
            unsafe_allow_html=True,
        )

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        height=height,
        column_config=columns_config or {},
    )
    if caption:
        st.caption(caption)


__all__ = ["ranking_table"]
