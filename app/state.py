"""state · st.session_state 集中封装(开发规范§10.3)。

跨页/跨交互状态统一在此(组合/筛选条件/模拟账本/评分权重)，避免散落全局可变变量。
模拟交易、组合构建在无后端时用 session_state 本地记账，刷新保持、可重置(原型⑤⑥)。
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from app.mock import store


def get(key: str, default: Any = None) -> Any:
    """读取 session_state，缺失返回 default。"""
    return st.session_state.get(key, default)


def set(key: str, value: Any) -> None:
    """写入 session_state。"""
    st.session_state[key] = value


def ensure(key: str, factory: Any) -> Any:
    """若不存在则用 factory 初始化(惰性默认)。"""
    if key not in st.session_state:
        st.session_state[key] = factory() if callable(factory) else factory
    return st.session_state[key]


# -----------------------------------------------------------------
# 模拟交易账本(原型⑤；本地记账，不连通实盘 §10 非目标)
# 初始化为 mock 初始持仓，买卖在本地增删;reset 清零。
# -----------------------------------------------------------------
def paper_account() -> dict[str, Any]:
    """模拟账户(现金/市值/收益)。"""
    return ensure("paper_account", lambda: dict(store.PAPER_ACCOUNT))


def paper_positions() -> list[dict[str, Any]]:
    """模拟持仓列表(买卖时增删行)。"""
    return ensure("paper_positions", lambda: list(store.PAPER_POSITIONS))


def paper_trades() -> list[dict[str, Any]]:
    """交易流水(复盘用，BR-4.5)。"""
    return ensure("paper_trades", lambda: [])


def reset_paper() -> None:
    """重置模拟账户(需二次确认，FR-15/DC-005)。"""
    st.session_state["paper_account"] = dict(store.PAPER_ACCOUNT)
    st.session_state["paper_positions"] = list(store.PAPER_POSITIONS)
    st.session_state["paper_trades"] = []


# -----------------------------------------------------------------
# 组合构建(原型⑥；本地构建，可从模拟持仓导入)
# -----------------------------------------------------------------
def portfolio_components() -> list[dict[str, Any]]:
    return ensure("portfolio_components", lambda: list(store.PORTFOLIO_COMPONENTS))


def reset_portfolio() -> None:
    st.session_state["portfolio_components"] = list(store.PORTFOLIO_COMPONENTS)


# -----------------------------------------------------------------
# 评分权重(原型③ 权重微调滑杆；默认 TP-01 §3.1 DEFAULT_WEIGHTS)
# -----------------------------------------------------------------
def score_weights() -> dict[str, float]:
    return ensure("score_weights", lambda: dict(store.DEFAULT_WEIGHTS))


def reset_score_weights() -> None:
    st.session_state["score_weights"] = dict(store.DEFAULT_WEIGHTS)


# -----------------------------------------------------------------
# 筛选条件(原型④；左表单 AND/OR)
# -----------------------------------------------------------------
def screen_filters() -> dict[str, Any]:
    return ensure(
        "screen_filters",
        lambda: {
            "logic": "AND",
            "fund_type": "all",
            "max_drawdown": 15.0,
            "min_return": 10.0,
            "min_tenure": 5,
            "theme": "不限",
        },
    )


# -----------------------------------------------------------------
# 选中的基金(跨页跳转：数据中心->评估详情->模拟)
# -----------------------------------------------------------------
def selected_fund() -> str | None:
    return get("selected_fund")


def select_fund(code: str) -> None:
    st.session_state["selected_fund"] = code
