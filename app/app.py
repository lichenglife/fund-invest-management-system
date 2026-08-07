"""FundLens Streamlit 入口(详设§2.7 纯 Python；原型§2 信息架构)。

顶部栏：系统名 + 角色切换(学习者/评估者/交易者) + 数据截至日期(原型§2)。
落地引导至仪表盘；侧边由 Streamlit 原生 pages/ 提供 12 模块 + 后台管理导航。

运行：``streamlit run app/app.py``
"""

from __future__ import annotations

import sys
from pathlib import Path

# 仓库根加入 sys.path，使 app/ 可 import config/schemas(本地开发)
_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import streamlit as st  # noqa: E402

from app.api_client import health, is_mock  # noqa: E402
from app.components.ui import inject_global_style, page_header  # noqa: E402
from app.utils import mock_badge, status_badge  # noqa: E402


def render_topbar() -> None:
    """顶部栏：绿色品牌条(原型§2) + 角色切换 + 数据截至。

    绿色 bar 全宽 bleed(logo 左 / 数据截至 右)，角色切换用 segmented_control
    (无则 selectbox)置于栏下，功能保持写入 session_state["role"]。
    """
    st.markdown(
        '<div class="fl-topbar">'
        '<div class="fl-logo">🟢 FundLens · 基金学习利器</div>'
        '<div class="fl-asof">数据截至 2025-07-20（净值 T+1 / 宏观 T+15）</div>'
        "</div>",
        unsafe_allow_html=True,
    )
    roles = ["学习者", "评估者", "交易者"]
    if "role" not in st.session_state:
        st.session_state.role = "学习者"
    with st.container():
        st.markdown('<div class="fl-topbar-role"></div>', unsafe_allow_html=True)
        if hasattr(st, "segmented_control"):
            st.segmented_control(
                "角色切换", roles, default=st.session_state.role, key="role"
            )
        else:
            st.selectbox(
                "角色切换",
                roles,
                index=roles.index(st.session_state.role),
                key="role",
            )


def render_status() -> None:
    """API 健康状态指示(§8.5 降级：失败不阻断)。"""
    data = health()
    ok = data is not None
    with st.sidebar:
        st.markdown(f"**后端状态** {status_badge(ok)}")
        if ok and data:
            st.caption(f"v{data.get('version', '?')} · {data.get('env', '?')}")
        else:
            st.caption("后端未就绪，展示示例数据")
        if is_mock():
            st.info(mock_badge())


def main() -> None:
    st.set_page_config(
        page_title="FundLens · 基金评估与模拟交易系统",
        page_icon="📈",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    inject_global_style()
    render_topbar()
    render_status()

    st.divider()
    page_header(
        "欢迎使用 FundLens",
        "覆盖 学 -> 懂 -> 筛 -> 练 -> 评 -> 穿 12 个功能模块 + 后台管理 · 从左侧导航选择模块进入",
    )

    with st.container(border=True):
        st.markdown("**快速入口**")
        pc = st.columns(3)
        pc[0].page_link("pages/01_仪表盘.py", label="📊 仪表盘", icon="➡️")
        pc[1].page_link("pages/04_智能筛选器.py", label="🔍 智能筛选", icon="➡️")
        pc[2].page_link("pages/05_模拟交易.py", label="💰 模拟交易", icon="➡️")

    st.caption("仅供参考，不构成投资建议（详细设计 §5.2）")


if __name__ == "__main__":
    main()
