"""components.score_panel · 五因子评分卡(原型③；P1-14a；TP-01 §3.1)。

五因子 ret/risk/perf/scale/manager(口径见 CLAUDE.md §4 红线，E4/E5)：
- 默认权重 30/25/20/15/10(TP-01 §3.1 DEFAULT_WEIGHTS；权重和=1，可调)。
- 滑杆微调 -> 即时加权重算 composite(分位表不变，ADR-002 唯一权威源)。
- 横截面按 asset_class 分组(子分百分位)。

> 评估引擎为全站唯一评分权威源(BR-2.12/ADR-002)；权重仅在评估详情调节，
> 筛选器/仪表盘只读引用，保证一致。
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from app import state, utils
from app.components.ui import panel
from app.mock import store


def _factor_bar(name: str, sub_score: float, weight: float, raw: float, contrib: float) -> None:
    """单因子分解条(原型 .factor：标签 + 进度条 + 贡献值)。"""
    meta = store.FACTOR_META.get(name, {"name": name, "desc": ""})
    label = f"{meta['name']} {int(weight * 100)}%"
    raw_str = utils.format_pct(raw) if name in ("ret", "risk") else f"{raw:g}"
    st.markdown(
        f'<div style="display:flex;justify-content:space-between;font-size:12px;color:#6b7785">'
        f"<span>{label}</span><span>{raw_str} · 贡献 {contrib:g}</span></div>",
        unsafe_allow_html=True,
    )
    st.progress(min(max(sub_score / 100, 0.0), 1.0))


def render(score: dict[str, Any], allow_tune: bool = True) -> float:
    """渲染五因子评分卡；返回当前 composite(可调权重后重算)。

    Args:
        score: get_score() 返回的评分数据(含 factors/weights)。
        allow_tune: 是否允许权重微调滑杆(评估详情 True；筛选/仪表盘只读 False)。
    """
    factors: dict[str, Any] = score.get("factors", {})
    weights = state.score_weights() if allow_tune else dict(store.DEFAULT_WEIGHTS)

    with panel("多因子综合评分", tag="引擎唯一权威源 FR-07 · ADR-002"):
        composite = utils.weighted_composite(factors, weights)
        st.markdown(
            f'<div style="font-size:34px;font-weight:800;color:{utils.COLOR_GREEN}">'
            f'{composite:g}<span style="font-size:14px;color:#6b7785">/100</span></div>',
            unsafe_allow_html=True,
        )
        for name in ("ret", "risk", "perf", "scale", "manager"):
            f = factors.get(name)
            if not f:
                continue
            _factor_bar(
                name,
                float(f["sub_score"]),
                weights.get(name, 0.0),
                float(f["raw"]),
                float(f["contrib"]),
            )

        st.caption("默认权重 30/25/20/15/10 · 见 TP-01 §3.1 · 横截面按 asset_class 分组")

        if allow_tune:
            st.markdown("**权重微调(拖动即重算)**")
            new_w: dict[str, float] = {}
            cols = st.columns(5)
            for col, name in zip(cols, ("ret", "risk", "perf", "scale", "manager"), strict=False):
                meta = store.FACTOR_META.get(name, {"name": name})
                with col:
                    v = st.slider(
                        meta["name"],
                        0,
                        100,
                        int(weights.get(name, 0.0) * 100),
                        key=f"w_{name}",
                    )
                    new_w[name] = v / 100.0
            # 归一化(权重和=1)并写回 session_state，下次渲染即用新权重
            total = sum(new_w.values()) or 1.0
            new_w = {k: v / total for k, v in new_w.items()}
            st.session_state["score_weights"] = new_w
            composite = utils.weighted_composite(factors, new_w)
            st.warning("⚠ 评估引擎为全站唯一评分权威源(BR-2.12)，权重仅在评估详情调节，保证一致。")
            st.caption(f"重算综合评分：**{composite:g}**")

    return composite
