"""components.brinson_chart · Brinson 归因图(原型③；P1-14b；TP-01 §3.5)。

三向分解：allocation(配置)/selection(选股)/interaction(交互)；
多期几何链接(Carino/Frongello)；用披露真实权重+OTHER_CASH 残差桶(E1/E2)。

边界(原型③ BR-2.4)：
- 仅 mixed/stock 显示归因；
- index/etf -> 跟踪误差/信息比率替代；
- bond -> 不显示。
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from app import utils
from app.components.ui import panel, source_footer
from app.mock import store


def render(attribution: dict[str, Any], fund_type: str = "mix") -> None:
    """渲染 Brinson 归因；按 fund_type 处理边界(原型③)。"""
    with panel("Brinson 归因", tag="仅主动股混基 · BR-2.4 · TP-01 §3.5"):
        if fund_type in ("index", "etf"):
            st.info(store.ATTRIBUTION_SUBSTITUTE[fund_type])
            return
        if fund_type == "bond":
            st.info(store.ATTRIBUTION_SUBSTITUTE["bond"])
            return

        if not attribution:
            st.warning("持仓披露缺失 -> unavailable(无法归因)")
            return

        a = float(attribution.get("allocation", 0.0))
        s = float(attribution.get("selection", 0.0))
        i = float(attribution.get("interaction", 0.0))
        active = float(attribution.get("active_return", a + s + i))

        df = pd.DataFrame(
            {
                "超额收益拆项": ["配置收益", "选股收益", "交互收益", "主动收益合计"],
                "数值": [a, s, i, active],
                "说明": [
                    "行业/个股超配带来的超额",
                    "主要靠选股能力",
                    "配置×选股",
                    "三效应之和(几何链接复利主动收益)",
                ],
            }
        )
        df["数值"] = df["数值"].apply(utils.format_pct)
        st.dataframe(df, use_container_width=True, hide_index=True)

        # 三效应柱状图(原型归因可视化)
        chart_df = pd.DataFrame(
            {
                "效应": ["配置", "选股", "交互"],
                "超额收益": [a, s, i],
            }
        )
        st.bar_chart(chart_df.set_index("效应"), use_container_width=True)

        st.caption(
            "用披露真实权重 + OTHER_CASH 残差桶(基金/基准各匹配)；"
            "多期几何链接(Carino/Frongello)(E1/E2)"
        )
        source_footer(extra=f"scope={attribution.get('scope', 'mixed/stock')}")
