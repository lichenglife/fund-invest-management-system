"""FundLens Streamlit 入口(详设§2.7 纯 Python；原型§2 信息架构)。

顶部栏：系统名 + 角色切换(学习者/评估者/交易者) + 数据截至日期(原型§2)。
落地引导至仪表盘；侧边由 Streamlit 原生 pages/ 提供 12 模块导航。

运行：``streamlit run app/app.py``
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

# 仓库根加入 sys.path，使 app/ 可 import config/schemas(本地开发)
_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import streamlit as st  # noqa: E402
from api_client import health  # noqa: E402
from utils import status_badge  # noqa: E402


def render_topbar() -> None:
    """顶部栏：系统名 + 角色切换 + 数据截至(原型§2)。"""
    cols = st.columns([6, 2, 2])
    with cols[0]:
        st.markdown("### 📈 FundLens · 基金学习利器")
    with cols[1]:
        st.selectbox("角色", ["学习者", "评估者", "交易者"], key="role")
    with cols[2]:
        # 数据截至日期占位(真实值由 P1-12 仪表盘聚合接口提供)
        st.caption(f"数据截至 {date.today().isoformat()}")


def render_status() -> None:
    """API 健康状态指示(§8.5 降级：失败不阻断)。"""
    data = health()
    ok = data is not None
    with st.sidebar:
        st.markdown(f"**后端状态** {status_badge(ok)}")
        if ok and data:
            st.caption(f"v{data.get('version', '?')} · {data.get('env', '?')}")
        else:
            st.caption("后端未就绪，仅展示占位")


def main() -> None:
    st.set_page_config(
        page_title="FundLens · 基金评估与模拟交易系统",
        page_icon="📈",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    render_topbar()
    render_status()

    st.divider()
    st.markdown("#### 欢迎使用 FundLens")
    st.markdown(
        "覆盖 **学 → 懂 → 筛 → 练 → 评 → 穿** 12 个功能模块。"
        "请从左侧导航选择模块进入。当前为 **Phase 0 工程骨架**，各模块占位待实现。"
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
