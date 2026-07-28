"""state · st.session_state 集中封装(开发规范§10.3)。

跨页/跨交互状态统一在此(组合/筛选条件/用户态)，避免散落全局可变变量。
"""

from __future__ import annotations

from typing import Any

import streamlit as st


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
