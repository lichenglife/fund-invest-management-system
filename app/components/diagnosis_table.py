"""components.diagnosis_table · 红黄绿诊断表(原型⑥；P1-17a；TP-03)。

多层级诊断：股债/海外/行业/风格/个基，每维 status+level(g/y/r)+可操作建议。
口径红线(CLAUDE.md §4 E8/E9/E12)：
- 股债目标仓位由 risk_type 推导(保守20-40/稳健40-60/进取60-80)；
- 止损=相对基准超额<−15% **或** 回撤>30% 红；
- 费率预警 > 2.0%。
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from app import utils
from app.components.ui import panel


def render(rows: list[dict[str, Any]], risk_type: str | None = None) -> None:
    """渲染红黄绿诊断报告(原型⑥ 自动多层级诊断 FR-37)。"""
    with panel("组合诊断报告", tag="自动 · 红黄绿 · FR-37 · TP-03"):
        if risk_type:
            st.caption(f"风险偏好判定：**{risk_type}**(股债目标仓位由 risk_type 推导，E8)")

        out = []
        for r in rows:
            out.append(
                {
                    "维度": r["dim"],
                    "现状": r["status"],
                    "状态": utils.level_row(r["level"]),
                    "可操作建议": r["advice"],
                }
            )
        df = pd.DataFrame(out)
        # 状态列着色：用 DataFrame 列样式不可直接渲染颜色，改用 markdown 表
        st.dataframe(df, use_container_width=True, hide_index=True)

        # 红线提示
        reds = [r for r in rows if r["level"] == "r"]
        if reds:
            for r in reds:
                st.error(f"🔴 {r['dim']}：{r['status']} -> {r['advice']}")
        st.caption("止损口径：相对基准超额 < −15% 或 回撤 > 30% 红；费率预警 > 2.0%(E9/E12)")
